#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Universal folder backup utility with compression and optional encryption.

This module provides a clean, Pythonic implementation for creating
compressed backups of any directory with optional password protection.

Usage:
    python -m utils.backup_folder <source_dir> [--output <output_path>]
                                     [--password] [--no-password]

Example:
    python -m utils.backup_folder /path/to/folder --output /backup/location
"""

import argparse
import getpass
import io
import shutil
import sys
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

# Constants following PEP 8
MAX_COMPRESSION_LEVEL = 9
CHUNK_SIZE = 8 * 1024 * 1024  # 8 MB
PROGRESS_UPDATE_INTERVAL = 10
DISK_SPACE_RESERVE_RATIO = 1.1
COMPRESSION_ESTIMATE_RATIO = 0.5
SCAN_PROGRESS_INTERVAL = 100


def setup_utf8_output() -> None:
    """Configure UTF-8 encoding for output streams (Windows only).

    This function is called only when the script is run directly,
    not when imported as a module, to avoid conflicts with pytest.
    """
    if sys.platform != 'win32':
        return

    try:
        if hasattr(sys.stdout, 'buffer') and hasattr(sys.stderr, 'buffer'):
            sys.stdout = io.TextIOWrapper(
                sys.stdout.buffer,
                encoding='utf-8',
                line_buffering=True
            )
            sys.stderr = io.TextIOWrapper(
                sys.stderr.buffer,
                encoding='utf-8',
                line_buffering=True
            )
            sys.stdout.flush()
            sys.stderr.flush()
    except (AttributeError, OSError, ValueError):
        pass


@dataclass
class ArchiveStats:
    """Statistics for archive creation process."""

    total_files: int = 0
    processed_files: int = 0
    total_size: int = 0
    processed_size: int = 0
    archive_size: int = 0
    skipped_files: int = 0

    @property
    def compression_ratio(self) -> float:
        """Calculate compression ratio as percentage.

        Returns:
            Compression ratio in percent (0-100).
        """
        if self.total_size == 0:
            return 0.0
        return (1 - self.archive_size / self.total_size) * 100.0

    @property
    def progress_percent(self) -> float:
        """Calculate processing progress as percentage.

        Returns:
            Progress in percent (0-100).
        """
        if self.total_size == 0:
            return 0.0
        return (self.processed_size / self.total_size) * 100.0


class ZipArchiveManager:
    """Manager for ZIP archive operations with optional encryption.

    Supports pyzipper for AES encryption with fallback to standard zipfile
    when pyzipper is not available.
    """

    def __init__(self, use_password: bool = False) -> None:
        """Initialize archive manager.

        Args:
            use_password: Enable password encryption if available.
        """
        self.use_password = use_password
        self.zip_class = self._get_zip_class()
        self.compression_type = self._get_compression_type()

    def _get_zip_class(self) -> type:
        """Get appropriate ZIP class for encryption support.

        Returns:
            ZIP class (pyzipper.AESZipFile or zipfile.ZipFile).
        """
        if not self.use_password:
            return zipfile.ZipFile

        try:
            import pyzipper  # type: ignore[import-untyped]
            return pyzipper.AESZipFile
        except ImportError:
            self.use_password = False
            return zipfile.ZipFile

    def _get_compression_type(self) -> int:
        """Get compression type constant.

        Returns:
            Compression type (ZIP_DEFLATED).
        """
        return zipfile.ZIP_DEFLATED

    def create_archive_kwargs(self) -> dict:
        """Create keyword arguments for archive creation.

        Returns:
            Dictionary with compression and encryption settings.
        """
        kwargs = {
            'compression': self.compression_type,
            'compresslevel': MAX_COMPRESSION_LEVEL,
        }

        if self.use_password:
            try:
                import pyzipper  # type: ignore[import-untyped]
                kwargs['encryption'] = pyzipper.WZ_AES
            except ImportError:
                pass

        return kwargs

    def create_archive(
        self,
        backup_path: Path,
        password: Optional[bytes] = None
    ) -> zipfile.ZipFile:
        """Create archive context manager.

        Args:
            backup_path: Path to archive file.
            password: Optional password for encryption.

        Returns:
            ZIP archive context manager.
        """
        kwargs = self.create_archive_kwargs()
        archive = self.zip_class(backup_path, 'w', **kwargs)

        if self.use_password and password:
            archive.setpassword(password)

        return archive


class FileProcessor:
    """File processor for efficient reading of files during archiving."""

    def __init__(self, chunk_size: int = CHUNK_SIZE) -> None:
        """Initialize file processor.

        Args:
            chunk_size: Size of chunks for reading large files.
        """
        self.chunk_size = chunk_size

    def read_file_chunked(self, file_path: Path) -> bytes:
        """Read file in chunks for memory efficiency.

        Args:
            file_path: Path to file to read.

        Returns:
            Complete file contents as bytes.

        Raises:
            OSError: If file cannot be read.
        """
        file_data = bytearray()

        with open(file_path, 'rb') as file:
            while True:
                chunk = file.read(self.chunk_size)
                if not chunk:
                    break
                file_data.extend(chunk)

        return bytes(file_data)

    def read_file_direct(self, file_path: Path) -> bytes:
        """Read small file directly.

        Args:
            file_path: Path to file to read.

        Returns:
            File contents as bytes.
        """
        return file_path.read_bytes()


class BackupCreator:
    """Creator for directory backups with progress tracking."""

    def __init__(
        self,
        source_dir: Path,
        backup_path: Path,
        password: Optional[bytes] = None,
        progress_callback: Optional[Callable[[ArchiveStats], None]] = None
    ) -> None:
        """Initialize backup creator.

        Args:
            source_dir: Directory to backup.
            backup_path: Path for output archive.
            password: Optional password for encryption.
            progress_callback: Optional callback for progress updates.
        """
        self.source_dir = source_dir
        self.backup_path = backup_path
        self.password = password
        self.progress_callback = progress_callback
        self.stats = ArchiveStats()
        self.archive_manager = ZipArchiveManager(
            use_password=password is not None
        )
        self.file_processor = FileProcessor()
        self._file_sizes: dict[Path, int] = {}

    def validate_source(self) -> None:
        """Validate source directory exists and is a directory.

        Raises:
            FileNotFoundError: If directory does not exist.
            ValueError: If path is not a directory.
        """
        if not self.source_dir.exists():
            raise FileNotFoundError(
                f"Source directory not found: {self.source_dir}"
            )

        if not self.source_dir.is_dir():
            raise ValueError(
                f"Path is not a directory: {self.source_dir}"
            )

    def calculate_total_size(self) -> None:
        """Calculate total size of files to archive.

        Scans directory recursively and caches file sizes for later use.
        Provides progress updates during scanning.

        Raises:
            KeyboardInterrupt: If interrupted by user (Ctrl+C).
        """
        if not self.source_dir.exists():
            return

        files_scanned = 0

        try:
            for file_path in self.source_dir.rglob('*'):
                if not file_path.is_file():
                    continue

                try:
                    file_size = file_path.stat().st_size
                    self._file_sizes[file_path] = file_size
                    self.stats.total_size += file_size
                    self.stats.total_files += 1
                    files_scanned += 1

                    if files_scanned % SCAN_PROGRESS_INTERVAL == 0:
                        print(
                            f"Scanning: {self.stats.total_files} files "
                            f"({format_size(self.stats.total_size)})...",
                            flush=True
                        )
                except (OSError, PermissionError):
                    continue

        except KeyboardInterrupt:
            print("\n\nScanning interrupted by user.", flush=True)
            raise

    def check_disk_space(self) -> None:
        """Check available disk space for archive.

        Raises:
            OSError: If insufficient disk space available.
        """
        backup_parent = self.backup_path.parent

        if not backup_parent.exists():
            return

        stat = shutil.disk_usage(backup_parent)
        free_space = stat.free
        estimated_size = int(
            self.stats.total_size
            * COMPRESSION_ESTIMATE_RATIO
            * DISK_SPACE_RESERVE_RATIO
        )

        if free_space < estimated_size:
            raise OSError(
                f"Insufficient disk space. "
                f"Required: {format_size(estimated_size)}, "
                f"Available: {format_size(free_space)}"
            )

    def _add_file_to_archive(
        self,
        archive: zipfile.ZipFile,
        file_path: Path,
        arcname: str
    ) -> bool:
        """Add file to archive.

        Args:
            archive: ZIP archive object.
            file_path: Path to file to add.
            arcname: Name for file in archive.

        Returns:
            True if successful, False if skipped.
        """
        try:
            file_size = self._file_sizes.get(file_path)

            if file_size is None:
                try:
                    file_size = file_path.stat().st_size
                except (OSError, PermissionError):
                    self.stats.skipped_files += 1
                    return False

            if file_size > CHUNK_SIZE:
                file_data = self.file_processor.read_file_chunked(file_path)
            else:
                file_data = self.file_processor.read_file_direct(file_path)

            archive.writestr(
                arcname,
                file_data,
                compress_type=self.archive_manager.compression_type,
                compresslevel=MAX_COMPRESSION_LEVEL
            )

            self.stats.processed_files += 1
            self.stats.processed_size += file_size
            return True

        except (OSError, PermissionError):
            self.stats.skipped_files += 1
            return False

    def create_archive(self) -> None:
        """Create archive from source directory.

        Raises:
            FileNotFoundError: If source directory does not exist.
            PermissionError: If access denied.
            KeyboardInterrupt: If interrupted by user (Ctrl+C).
        """
        try:
            self.validate_source()
            self.calculate_total_size()
            self.check_disk_space()
        except KeyboardInterrupt:
            print(
                "\n\nOperation interrupted during preparation.",
                flush=True
            )
            raise

        try:
            with self.archive_manager.create_archive(
                self.backup_path,
                self.password
            ) as archive:
                if self.progress_callback:
                    self.progress_callback(self.stats)

                try:
                    for file_path in self._file_sizes:
                        arcname = file_path.relative_to(self.source_dir)
                        self._add_file_to_archive(
                            archive,
                            file_path,
                            str(arcname)
                        )

                        if (self.stats.processed_files
                                % PROGRESS_UPDATE_INTERVAL == 0):
                            if self.progress_callback:
                                self.progress_callback(self.stats)

                except KeyboardInterrupt:
                    print(
                        "\n\nArchiving interrupted by user.",
                        flush=True
                    )
                    print(
                        f"Processed: {self.stats.processed_files}/"
                        f"{self.stats.total_files} files",
                        flush=True
                    )
                    if self.stats.processed_size > 0:
                        print(
                            f"Size processed: "
                            f"{format_size(self.stats.processed_size)}",
                            flush=True
                        )
                    raise

                if (self.stats.processed_files
                        % PROGRESS_UPDATE_INTERVAL != 0):
                    if self.progress_callback:
                        self.progress_callback(self.stats)

                if self.backup_path.exists():
                    self.stats.archive_size = self.backup_path.stat().st_size
                else:
                    self.stats.archive_size = 0

        except KeyboardInterrupt:
            if self.backup_path.exists():
                try:
                    self.backup_path.unlink()
                    print(
                        f"Incomplete archive removed: {self.backup_path}",
                        flush=True
                    )
                except Exception:
                    pass
            raise


def format_backup_name(source_name: str) -> str:
    """Generate backup archive name from source directory name.

    Args:
        source_name: Name of source directory.

    Returns:
        Archive name in format: {source_name}_DD-MM-YYYY_HH-MM
    """
    now = datetime.now()
    date_str = now.strftime('%d-%m-%Y')
    time_str = now.strftime('%H-%M')
    return f"{source_name}_{date_str}_{time_str}"


def format_size(size_bytes: int) -> str:
    """Format byte size into human-readable string.

    Args:
        size_bytes: Size in bytes.

    Returns:
        Formatted string with appropriate unit (B, KB, MB, GB, TB, PB).
    """
    units = ['B', 'KB', 'MB', 'GB', 'TB']
    size = float(size_bytes)

    for unit in units:
        if size < 1024.0:
            return f"{size:.2f} {unit}"
        size /= 1024.0

    return f"{size:.2f} PB"


def get_password() -> bytes:
    """Get password interactively from user.

    Returns:
        Password as bytes (UTF-8 encoded).

    Raises:
        ValueError: If password is empty or passwords don't match.
    """
    print("\n" + "=" * 60, flush=True)
    print("SET ARCHIVE PASSWORD", flush=True)
    print("=" * 60, flush=True)

    password = getpass.getpass("Enter archive password: ")

    if not password:
        raise ValueError("Password cannot be empty")

    password_confirm = getpass.getpass("Confirm password: ")

    if password != password_confirm:
        raise ValueError("Passwords do not match")

    print("✓ Password set", flush=True)
    return password.encode('utf-8')


def print_progress(stats: ArchiveStats) -> None:
    """Print archiving progress.

    Args:
        stats: Archive statistics.
    """
    print(
        f"Processed: {stats.processed_files}/{stats.total_files} files "
        f"({stats.progress_percent:.1f}%) - "
        f"{format_size(stats.processed_size)}",
        flush=True
    )


def print_archive_info(
    stats: ArchiveStats,
    backup_path: Path,
    use_password: bool
) -> None:
    """Print archive creation summary.

    Args:
        stats: Archive statistics.
        backup_path: Path to created archive.
        use_password: Whether password encryption was used.
    """
    print("\n" + "=" * 60, flush=True)
    print("ARCHIVING COMPLETED", flush=True)
    print("=" * 60, flush=True)
    print(
        f"Files processed: {stats.processed_files}/{stats.total_files}",
        flush=True
    )

    if stats.skipped_files > 0:
        print(f"Files skipped: {stats.skipped_files}", flush=True)

    print(f"Original size: {format_size(stats.total_size)}", flush=True)
    print(f"Archive size: {format_size(stats.archive_size)}", flush=True)
    print(
        f"Compression ratio: {stats.compression_ratio:.1f}%",
        flush=True
    )

    if use_password:
        print("✓ Archive protected with password (AES-256)", flush=True)

    print(f"Archive saved: {backup_path}", flush=True)


def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments.

    Returns:
        Parsed arguments namespace.
    """
    parser = argparse.ArgumentParser(
        description='Create compressed backup of a directory',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        'source_dir',
        type=Path,
        help='Source directory to backup'
    )

    parser.add_argument(
        '--output',
        '-o',
        type=Path,
        help='Output directory for archive (default: parent of source)'
    )

    parser.add_argument(
        '--password',
        action='store_true',
        help='Enable password protection (interactive)'
    )

    parser.add_argument(
        '--no-password',
        action='store_true',
        help='Disable password protection (default)'
    )

    return parser.parse_args()


def main() -> int:
    """Main entry point for backup script.

    Returns:
        Exit code: 0 for success, 1 for error.
    """
    try:
        args = parse_arguments()

        source_dir = args.source_dir.resolve()
        output_dir = args.output.resolve() if args.output else source_dir.parent
        use_password = args.password and not args.no_password

        print("=" * 60, flush=True)
        print("FOLDER BACKUP UTILITY", flush=True)
        print("=" * 60, flush=True)

        if not source_dir.exists():
            print(f"Error: Directory not found: {source_dir}", flush=True)
            return 1

        if not source_dir.is_dir():
            print(f"Error: Path is not a directory: {source_dir}", flush=True)
            return 1

        source_name = source_dir.name
        backup_name = format_backup_name(source_name)
        backup_path = output_dir / f"{backup_name}.zip"

        if backup_path.exists():
            print(
                f"Warning: Archive already exists: {backup_path}",
                flush=True
            )
            response = input("Overwrite? (y/N): ").strip().lower()

            if response != 'y':
                print("Operation cancelled.", flush=True)
                return 0

            backup_path.unlink()

        password: Optional[bytes] = None

        if use_password:
            try:
                password = get_password()
            except ValueError as error:
                print(f"Error: {error}", flush=True)
                return 1
            except KeyboardInterrupt:
                print("\n\nOperation cancelled by user.", flush=True)
                return 0

            try:
                import pyzipper  # noqa: F401  # type: ignore[import-untyped]
            except ImportError:
                print(
                    "\nWARNING: pyzipper library not installed.",
                    flush=True
                )
                print("Archive will be created WITHOUT password.", flush=True)
                print("To install: pip install pyzipper", flush=True)
                use_password = False
                password = None

        print("\n" + "=" * 60, flush=True)
        print("STARTING ARCHIVING", flush=True)
        print("=" * 60, flush=True)
        print(f"Source: {source_dir}", flush=True)
        print(f"Archive: {backup_path}", flush=True)
        print(
            f"Compression: maximum (level {MAX_COMPRESSION_LEVEL})",
            flush=True
        )

        if use_password:
            print("Encryption: AES-256 with password", flush=True)
        else:
            print("Encryption: NONE", flush=True)

        print("\nStarting archiving...", flush=True)

        creator = BackupCreator(
            source_dir,
            backup_path,
            password,
            progress_callback=print_progress
        )

        try:
            creator.create_archive()
        except KeyboardInterrupt:
            print("\nOperation interrupted by user.", flush=True)
            return 1

        print_archive_info(creator.stats, backup_path, use_password)

        print("\n" + "=" * 60, flush=True)
        print("BACKUP SUCCESSFULLY CREATED", flush=True)
        print("=" * 60, flush=True)
        print(f"Path: {backup_path}", flush=True)
        print(f"Size: {format_size(backup_path.stat().st_size)}", flush=True)

        return 0

    except KeyboardInterrupt:
        print("\n\nOperation interrupted by user.", flush=True)
        return 1
    except (FileNotFoundError, PermissionError, OSError, ValueError) as error:
        print(f"\nError: {error}", flush=True)
        return 1
    except Exception as error:
        print(f"\nUnexpected error: {error}", flush=True)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    setup_utf8_output()
    sys.exit(main())

