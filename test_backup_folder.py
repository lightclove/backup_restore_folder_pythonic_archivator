#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unit tests for backup_folder.py.

Tests individual components:
- format_backup_name
- format_size
- FileProcessor
- ZipArchiveManager
- ArchiveStats
- BackupCreator
"""

import sys
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest

# Add project root to sys.path
project_root = Path(__file__).resolve().parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from utils.backup_folder import (
    ArchiveStats,
    BackupCreator,
    FileProcessor,
    ZipArchiveManager,
    format_backup_name,
    format_size,
    get_password,
    print_archive_info,
    print_progress,
)


class TestFormatBackupName:
    """Tests for format_backup_name function."""

    def test_format_backup_name_returns_string(self) -> None:
        """Test: function returns string."""
        result = format_backup_name("test_folder")
        assert isinstance(result, str)
        assert result.startswith("test_folder_")

    def test_format_backup_name_contains_date(self) -> None:
        """Test: name contains date in correct format."""
        result = format_backup_name("test")
        parts = result.split("_")
        assert len(parts) == 3
        assert parts[0] == "test"
        # Check date format DD-MM-YYYY
        date_parts = parts[1].split("-")
        assert len(date_parts) == 3
        assert len(date_parts[0]) == 2  # Day
        assert len(date_parts[1]) == 2  # Month
        assert len(date_parts[2]) == 4  # Year
        # Check time format HH-MM
        time_parts = parts[2].split("-")
        assert len(time_parts) == 2
        assert len(time_parts[0]) == 2  # Hours
        assert len(time_parts[1]) == 2  # Minutes


class TestFormatSize:
    """Tests for format_size function."""

    def test_format_size_bytes(self) -> None:
        """Test: formatting bytes."""
        assert format_size(0) == "0.00 B"
        assert format_size(512) == "512.00 B"
        assert format_size(1023) == "1023.00 B"

    def test_format_size_kilobytes(self) -> None:
        """Test: formatting kilobytes."""
        result = format_size(1024)
        assert "KB" in result
        assert float(result.split()[0]) > 0

    def test_format_size_megabytes(self) -> None:
        """Test: formatting megabytes."""
        result = format_size(1024 * 1024)
        assert "MB" in result
        assert float(result.split()[0]) > 0

    def test_format_size_gigabytes(self) -> None:
        """Test: formatting gigabytes."""
        result = format_size(1024 * 1024 * 1024)
        assert "GB" in result
        assert float(result.split()[0]) > 0

    def test_format_size_terabytes(self) -> None:
        """Test: formatting terabytes."""
        result = format_size(1024 * 1024 * 1024 * 1024)
        assert "TB" in result
        assert float(result.split()[0]) > 0


class TestArchiveStats:
    """Tests for ArchiveStats dataclass."""

    def test_archive_stats_initialization(self) -> None:
        """Test: statistics initialization."""
        stats = ArchiveStats()
        assert stats.total_files == 0
        assert stats.processed_files == 0
        assert stats.total_size == 0
        assert stats.processed_size == 0
        assert stats.archive_size == 0
        assert stats.skipped_files == 0

    def test_compression_ratio_zero_size(self) -> None:
        """Test: compression ratio with zero size."""
        stats = ArchiveStats()
        assert stats.compression_ratio == 0.0

    def test_compression_ratio_calculation(self) -> None:
        """Test: compression ratio calculation."""
        stats = ArchiveStats(
            total_size=1000,
            archive_size=500
        )
        assert stats.compression_ratio == 50.0

    def test_progress_percent_zero_size(self) -> None:
        """Test: progress with zero size."""
        stats = ArchiveStats()
        assert stats.progress_percent == 0.0

    def test_progress_percent_calculation(self) -> None:
        """Test: progress calculation."""
        stats = ArchiveStats(
            total_size=1000,
            processed_size=500
        )
        assert stats.progress_percent == 50.0

    def test_progress_percent_100_percent(self) -> None:
        """Test: 100% progress."""
        stats = ArchiveStats(
            total_size=1000,
            processed_size=1000
        )
        assert stats.progress_percent == 100.0


class TestFileProcessor:
    """Tests for FileProcessor class."""

    def test_file_processor_initialization(self) -> None:
        """Test: file processor initialization."""
        processor = FileProcessor()
        assert processor.chunk_size > 0

    def test_file_processor_custom_chunk_size(self) -> None:
        """Test: custom chunk size."""
        processor = FileProcessor(chunk_size=1024)
        assert processor.chunk_size == 1024

    def test_read_file_direct_small_file(self, tmp_path: Path) -> None:
        """Test: reading small file directly."""
        test_file = tmp_path / "test.txt"
        test_content = b"Hello, World!"
        test_file.write_bytes(test_content)

        processor = FileProcessor()
        result = processor.read_file_direct(test_file)

        assert result == test_content

    def test_read_file_chunked_small_file(self, tmp_path: Path) -> None:
        """Test: reading small file in chunks."""
        test_file = tmp_path / "test.txt"
        test_content = b"Hello, World!"
        test_file.write_bytes(test_content)

        processor = FileProcessor(chunk_size=5)
        result = processor.read_file_chunked(test_file)

        assert result == test_content

    def test_read_file_chunked_large_file(self, tmp_path: Path) -> None:
        """Test: reading large file in chunks."""
        test_file = tmp_path / "large.txt"
        large_content = b"X" * (10 * 1024)  # 10 KB
        test_file.write_bytes(large_content)

        processor = FileProcessor(chunk_size=1024)
        result = processor.read_file_chunked(test_file)

        assert result == large_content
        assert len(result) == len(large_content)

    def test_read_file_direct_nonexistent_file(
        self,
        tmp_path: Path
    ) -> None:
        """Test: reading nonexistent file."""
        processor = FileProcessor()
        nonexistent = tmp_path / "nonexistent.txt"

        with pytest.raises(FileNotFoundError):
            processor.read_file_direct(nonexistent)

    def test_read_file_chunked_nonexistent_file(
        self,
        tmp_path: Path
    ) -> None:
        """Test: reading nonexistent file in chunks."""
        processor = FileProcessor()
        nonexistent = tmp_path / "nonexistent.txt"

        with pytest.raises(FileNotFoundError):
            processor.read_file_chunked(nonexistent)


class TestZipArchiveManager:
    """Tests for ZipArchiveManager class."""

    def test_zip_archive_manager_without_password(self) -> None:
        """Test: manager without password."""
        manager = ZipArchiveManager(use_password=False)
        assert manager.use_password is False
        assert manager.zip_class is not None
        assert manager.compression_type is not None

    @patch('builtins.__import__')
    def test_zip_archive_manager_with_password_no_pyzipper(
        self,
        mock_import
    ) -> None:
        """Test: manager with password without pyzipper (fallback)."""
        def import_side_effect(name, *args, **kwargs):
            if name == 'pyzipper':
                raise ImportError("No module named 'pyzipper'")
            return __import__(name, *args, **kwargs)

        mock_import.side_effect = import_side_effect

        manager = ZipArchiveManager(use_password=True)
        assert manager.use_password is False
        assert manager.zip_class == zipfile.ZipFile

    def test_create_archive_kwargs_without_password(self) -> None:
        """Test: archive kwargs without password."""
        manager = ZipArchiveManager(use_password=False)
        kwargs = manager.create_archive_kwargs()

        assert 'compression' in kwargs
        assert 'compresslevel' in kwargs
        assert kwargs['compresslevel'] == 9
        assert 'encryption' not in kwargs

    def test_create_archive_kwargs_with_password(self) -> None:
        """Test: archive kwargs with password."""
        try:
            import pyzipper  # type: ignore[import-untyped]
            manager = ZipArchiveManager(use_password=True)
            kwargs = manager.create_archive_kwargs()

            assert 'compression' in kwargs
            assert 'compresslevel' in kwargs
            assert 'encryption' in kwargs
        except ImportError:
            pytest.skip("pyzipper not installed")

    def test_create_archive_context_manager(self, tmp_path: Path) -> None:
        """Test: creating archive via context manager."""
        manager = ZipArchiveManager(use_password=False)
        archive_path = tmp_path / "test.zip"

        assert archive_path.exists() is False

        with manager.create_archive(archive_path) as archive:
            assert archive is not None
            assert archive_path.exists() is True

        assert archive_path.exists()


class TestGetPassword:
    """Tests for get_password function."""

    @patch('utils.backup_folder.getpass.getpass')
    def test_get_password_success(self, mock_getpass) -> None:
        """Test: successful password retrieval."""
        mock_getpass.side_effect = ["test_password", "test_password"]

        result = get_password()

        assert result == b"test_password"
        assert mock_getpass.call_count == 2

    @patch('utils.backup_folder.getpass.getpass')
    def test_get_password_empty(self, mock_getpass) -> None:
        """Test: empty password raises ValueError."""
        mock_getpass.return_value = ""

        with pytest.raises(ValueError, match="Password cannot be empty"):
            get_password()

    @patch('utils.backup_folder.getpass.getpass')
    def test_get_password_mismatch(self, mock_getpass) -> None:
        """Test: password mismatch raises ValueError."""
        mock_getpass.side_effect = ["password1", "password2"]

        with pytest.raises(ValueError, match="Passwords do not match"):
            get_password()


class TestPrintProgress:
    """Tests for print_progress function."""

    @patch('builtins.print')
    def test_print_progress(self, mock_print) -> None:
        """Test: printing archiving progress."""
        stats = ArchiveStats(
            total_files=100,
            processed_files=50,
            total_size=1000,
            processed_size=500
        )

        print_progress(stats)

        mock_print.assert_called_once()
        call_args = mock_print.call_args[0][0]
        assert "Processed: 50/100 files" in call_args
        assert "50.0%" in call_args


class TestPrintArchiveInfo:
    """Tests for print_archive_info function."""

    @patch('builtins.print')
    def test_print_archive_info_without_password(
        self,
        mock_print,
        tmp_path: Path
    ) -> None:
        """Test: printing archive info without password."""
        backup_path = tmp_path / "backup.zip"
        backup_path.touch()

        stats = ArchiveStats(
            total_files=10,
            processed_files=10,
            total_size=1000,
            archive_size=500
        )

        print_archive_info(stats, backup_path, use_password=False)

        assert mock_print.call_count >= 6
        calls = [str(call) for call in mock_print.call_args_list]
        assert any("ARCHIVING COMPLETED" in str(call) for call in calls)
        assert any("Files processed: 10/10" in str(call) for call in calls)

    @patch('builtins.print')
    def test_print_archive_info_with_password(
        self,
        mock_print,
        tmp_path: Path
    ) -> None:
        """Test: printing archive info with password."""
        backup_path = tmp_path / "backup.zip"
        backup_path.touch()

        stats = ArchiveStats(
            total_files=10,
            processed_files=10,
            total_size=1000,
            archive_size=500
        )

        print_archive_info(stats, backup_path, use_password=True)

        assert mock_print.call_count >= 7
        calls = [str(call) for call in mock_print.call_args_list]
        assert any("protected with password" in str(call) for call in calls)

    @patch('builtins.print')
    def test_print_archive_info_with_skipped_files(
        self,
        mock_print,
        tmp_path: Path
    ) -> None:
        """Test: printing archive info with skipped files."""
        backup_path = tmp_path / "backup.zip"
        backup_path.touch()

        stats = ArchiveStats(
            total_files=10,
            processed_files=8,
            skipped_files=2,
            total_size=1000,
            archive_size=500
        )

        print_archive_info(stats, backup_path, use_password=False)

        calls = [str(call) for call in mock_print.call_args_list]
        assert any("Files skipped: 2" in str(call) for call in calls)


class TestBackupCreator:
    """Tests for BackupCreator class."""

    def test_backup_creator_initialization(self, tmp_path: Path) -> None:
        """Test: BackupCreator initialization."""
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        backup_path = tmp_path / "backup.zip"

        creator = BackupCreator(source_dir, backup_path, None, None)

        assert creator.source_dir == source_dir
        assert creator.backup_path == backup_path
        assert creator.password is None
        assert creator.progress_callback is None

    def test_backup_creator_validate_source_not_exists(
        self,
        tmp_path: Path
    ) -> None:
        """Test: validating nonexistent directory."""
        source_dir = tmp_path / "nonexistent"
        backup_path = tmp_path / "backup.zip"

        creator = BackupCreator(source_dir, backup_path, None, None)

        with pytest.raises(FileNotFoundError):
            creator.validate_source()

    def test_backup_creator_validate_source_not_dir(
        self,
        tmp_path: Path
    ) -> None:
        """Test: validating file instead of directory."""
        source_file = tmp_path / "file.txt"
        source_file.touch()
        backup_path = tmp_path / "backup.zip"

        creator = BackupCreator(source_file, backup_path, None, None)

        with pytest.raises(ValueError, match="not a directory"):
            creator.validate_source()

    def test_backup_creator_validate_source_success(
        self,
        tmp_path: Path
    ) -> None:
        """Test: successful directory validation."""
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        backup_path = tmp_path / "backup.zip"

        creator = BackupCreator(source_dir, backup_path, None, None)
        creator.validate_source()  # Should not raise

    def test_backup_creator_calculate_total_size(
        self,
        tmp_path: Path
    ) -> None:
        """Test: calculating total file size."""
        source_dir = tmp_path / "source"
        source_dir.mkdir()

        file1 = source_dir / "file1.txt"
        file1.write_text("test content 1")
        file2 = source_dir / "file2.txt"
        file2.write_text("test content 2")

        backup_path = tmp_path / "backup.zip"
        creator = BackupCreator(source_dir, backup_path, None, None)

        creator.calculate_total_size()

        assert creator.stats.total_files == 2
        assert creator.stats.total_size > 0

    def test_backup_creator_create_archive_simple(
        self,
        tmp_path: Path
    ) -> None:
        """Test: creating simple archive without password."""
        source_dir = tmp_path / "source"
        source_dir.mkdir()

        test_file = source_dir / "test.txt"
        test_file.write_text("test content", encoding='utf-8')

        backup_path = tmp_path / "backup.zip"
        creator = BackupCreator(source_dir, backup_path, None, None)

        creator.create_archive()

        assert backup_path.exists()
        assert backup_path.stat().st_size > 0
        assert creator.stats.processed_files == 1
        assert creator.stats.archive_size > 0

    def test_backup_creator_calculate_total_size_keyboard_interrupt(
        self,
        tmp_path: Path
    ) -> None:
        """Test: KeyboardInterrupt handling in calculate_total_size()."""
        source_dir = tmp_path / "source"
        source_dir.mkdir()

        for i in range(5):
            (source_dir / f"file{i}.txt").write_text(f"content {i}")

        backup_path = tmp_path / "backup.zip"
        creator = BackupCreator(source_dir, backup_path, None, None)

        original_rglob = Path.rglob

        def mock_rglob(self, pattern):
            """Mock rglob that raises KeyboardInterrupt after first file."""
            files = list(original_rglob(self, pattern))
            yield files[0]
            raise KeyboardInterrupt("User interruption")

        with patch.object(Path, 'rglob', mock_rglob):
            with pytest.raises(KeyboardInterrupt):
                creator.calculate_total_size()

    def test_backup_creator_create_archive_keyboard_interrupt(
        self,
        tmp_path: Path
    ) -> None:
        """Test: KeyboardInterrupt handling in create_archive()."""
        source_dir = tmp_path / "source"
        source_dir.mkdir()

        for i in range(3):
            (source_dir / f"file{i}.txt").write_text(f"content {i}")

        backup_path = tmp_path / "backup.zip"
        creator = BackupCreator(source_dir, backup_path, None, None)
        creator.calculate_total_size()

        original_add_file = creator._add_file_to_archive
        call_count = [0]

        def mock_add_file(*args, **kwargs):
            """Mock _add_file_to_archive raising KeyboardInterrupt."""
            call_count[0] += 1
            if call_count[0] == 1:
                return original_add_file(*args, **kwargs)
            raise KeyboardInterrupt("User interruption")

        with patch.object(creator, '_add_file_to_archive', mock_add_file):
            with pytest.raises(KeyboardInterrupt):
                creator.create_archive()

        assert not backup_path.exists()
        assert creator.stats.processed_files == 1

    def test_backup_creator_create_archive_keyboard_interrupt_during_scanning(
        self,
        tmp_path: Path
    ) -> None:
        """Test: KeyboardInterrupt during file scanning."""
        source_dir = tmp_path / "source"
        source_dir.mkdir()

        (source_dir / "test.txt").write_text("test content")

        backup_path = tmp_path / "backup.zip"
        creator = BackupCreator(source_dir, backup_path, None, None)

        with patch.object(
            Path,
            'rglob',
            side_effect=KeyboardInterrupt("Interruption")
        ):
            with pytest.raises(KeyboardInterrupt):
                creator.create_archive()

        assert not backup_path.exists()

    def test_backup_creator_graceful_shutdown_cleanup(
        self,
        tmp_path: Path
    ) -> None:
        """Test: graceful shutdown with resource cleanup."""
        source_dir = tmp_path / "source"
        source_dir.mkdir()

        (source_dir / "test.txt").write_text("test content")

        backup_path = tmp_path / "backup.zip"
        creator = BackupCreator(source_dir, backup_path, None, None)
        creator.calculate_total_size()

        archive = creator.archive_manager.create_archive(backup_path, None)
        archive.__enter__()

        try:
            raise KeyboardInterrupt("Interruption")
        except KeyboardInterrupt:
            archive.__exit__(None, None, None)
            assert backup_path.exists()

            with patch.object(
                creator,
                '_add_file_to_archive',
                side_effect=KeyboardInterrupt("Interruption")
            ):
                with pytest.raises(KeyboardInterrupt):
                    creator.create_archive()

            assert not backup_path.exists()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

