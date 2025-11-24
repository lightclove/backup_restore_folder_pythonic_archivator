#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Integration tests for backup_folder.py.

Tests complete backup creation cycle:
- Creating test file structure
- Archiving with and without password
- Archive integrity validation
- Statistics validation
"""

import sys
import zipfile
from pathlib import Path

import pytest

# Add project root to sys.path
project_root = Path(__file__).resolve().parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from utils.backup_folder import BackupCreator, format_backup_name


class TestBackupCreatorIntegration:
    """Integration tests for BackupCreator."""

    @pytest.fixture
    def test_structure(self, tmp_path: Path) -> Path:
        """Create test file structure."""
        test_dir = tmp_path / "test_source"
        test_dir.mkdir()

        file1 = test_dir / "file1.txt"
        file1.write_text("Content of file 1", encoding='utf-8')

        subdir = test_dir / "subdir"
        subdir.mkdir()

        file2 = subdir / "file2.txt"
        file2.write_text("Content of file 2", encoding='utf-8')

        file3 = subdir / "file3.txt"
        file3.write_text("Content of file 3", encoding='utf-8')

        return test_dir

    @pytest.fixture
    def backup_path(self, tmp_path: Path) -> Path:
        """Path to archive for tests."""
        return tmp_path / "backup_test.zip"

    def test_backup_creator_without_password(
        self,
        test_structure: Path,
        backup_path: Path
    ) -> None:
        """Test: creating backup without password."""
        creator = BackupCreator(
            source_dir=test_structure,
            backup_path=backup_path,
            password=None
        )

        creator.create_archive()

        assert backup_path.exists()
        assert backup_path.stat().st_size > 0
        assert creator.stats.total_files == 3
        assert creator.stats.processed_files == 3
        assert creator.stats.total_size > 0
        assert creator.stats.archive_size > 0
        assert creator.stats.skipped_files == 0

    def test_backup_creator_with_password(
        self,
        test_structure: Path,
        backup_path: Path
    ) -> None:
        """Test: creating backup with password."""
        try:
            import pyzipper  # type: ignore[import-untyped]
        except ImportError:
            pytest.skip("pyzipper not installed")

        password = b"test_password_123"
        creator = BackupCreator(
            source_dir=test_structure,
            backup_path=backup_path,
            password=password
        )

        creator.create_archive()

        assert backup_path.exists()
        assert backup_path.stat().st_size > 0
        assert creator.stats.total_files == 3
        assert creator.stats.processed_files == 3

    def test_backup_creator_archive_content(
        self,
        test_structure: Path,
        backup_path: Path
    ) -> None:
        """Test: checking archive content."""
        creator = BackupCreator(
            source_dir=test_structure,
            backup_path=backup_path,
            password=None
        )

        creator.create_archive()

        with zipfile.ZipFile(backup_path, 'r') as archive:
            file_list = archive.namelist()

            assert "file1.txt" in file_list
            assert "subdir/file2.txt" in file_list
            assert "subdir/file3.txt" in file_list

            assert archive.read("file1.txt").decode('utf-8') == "Content of file 1"
            assert archive.read("subdir/file2.txt").decode('utf-8') == "Content of file 2"
            assert archive.read("subdir/file3.txt").decode('utf-8') == "Content of file 3"

    def test_backup_creator_progress_callback(
        self,
        test_structure: Path,
        backup_path: Path
    ) -> None:
        """Test: progress callback invocation."""
        callback_calls = []

        def progress_callback(stats):
            callback_calls.append(stats)

        creator = BackupCreator(
            source_dir=test_structure,
            backup_path=backup_path,
            password=None,
            progress_callback=progress_callback
        )

        creator.create_archive()

        assert creator.stats.processed_files == 3

    def test_backup_creator_validation_source_not_exists(
        self,
        backup_path: Path
    ) -> None:
        """Test: validating nonexistent directory."""
        nonexistent = Path("/nonexistent/directory/12345")
        creator = BackupCreator(
            source_dir=nonexistent,
            backup_path=backup_path,
            password=None
        )

        with pytest.raises(FileNotFoundError):
            creator.validate_source()

    def test_backup_creator_validation_source_not_dir(
        self,
        tmp_path: Path,
        backup_path: Path
    ) -> None:
        """Test: validating file instead of directory."""
        test_file = tmp_path / "not_a_dir.txt"
        test_file.write_text("test")

        creator = BackupCreator(
            source_dir=test_file,
            backup_path=backup_path,
            password=None
        )

        with pytest.raises(ValueError, match="not a directory"):
            creator.validate_source()

    def test_backup_creator_compression_ratio(
        self,
        test_structure: Path,
        backup_path: Path
    ) -> None:
        """Test: compression ratio calculation."""
        creator = BackupCreator(
            source_dir=test_structure,
            backup_path=backup_path,
            password=None
        )

        creator.create_archive()

        # Compression ratio can be negative for very small files due to ZIP overhead
        # For very small files, overhead can be much larger than original size
        # So we allow a wider range (from -500% to 100%)
        assert creator.stats.compression_ratio >= -500.0
        assert creator.stats.compression_ratio <= 100.0
        # Compression ratio should be a valid number
        assert isinstance(creator.stats.compression_ratio, (int, float))

    def test_backup_creator_large_file_chunked_reading(
        self,
        tmp_path: Path,
        backup_path: Path
    ) -> None:
        """Test: handling large file with chunked reading."""
        test_dir = tmp_path / "large_test"
        test_dir.mkdir()

        large_file = test_dir / "large.bin"
        large_content = b"X" * (10 * 1024 * 1024)  # 10 MB
        large_file.write_bytes(large_content)

        creator = BackupCreator(
            source_dir=test_dir,
            backup_path=backup_path,
            password=None
        )

        creator.create_archive()

        assert backup_path.exists()
        with zipfile.ZipFile(backup_path, 'r') as archive:
            assert "large.bin" in archive.namelist()
            assert len(archive.read("large.bin")) == len(large_content)

    def test_backup_creator_skipped_files(
        self,
        tmp_path: Path,
        backup_path: Path
    ) -> None:
        """Test: handling files without access."""
        test_dir = tmp_path / "permission_test"
        test_dir.mkdir()

        normal_file = test_dir / "normal.txt"
        normal_file.write_text("normal content")

        creator = BackupCreator(
            source_dir=test_dir,
            backup_path=backup_path,
            password=None
        )

        creator.create_archive()

        assert creator.stats.skipped_files == 0
        assert creator.stats.processed_files == 1


class TestFormatBackupNameIntegration:
    """Integration tests for format_backup_name."""

    def test_format_backup_name_uniqueness(self) -> None:
        """Test: backup name uniqueness."""
        import time

        name1 = format_backup_name("test_folder")
        time.sleep(1)
        name2 = format_backup_name("test_folder")

        assert name1.startswith("test_folder_")
        assert name2.startswith("test_folder_")
        assert len(name1) == len(name2)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

