#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Universal folder restore utility from ZIP backup archives.

This module provides a clean, Pythonic implementation for restoring
directories from compressed ZIP backups with optional password protection.

Usage:
    python -m utils.restore_folder <archive_path> [--output <output_dir>]
                                                 [--password]

Example:
    python -m utils.restore_folder backup.zip --output /restore/location
"""

import argparse
import getpass
import io
import shutil
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

# Constants following PEP 8
PROGRESS_UPDATE_INTERVAL = 10
CHUNK_SIZE = 8 * 1024 * 1024  # 8 MB


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
class RestoreStats:
    """Statistics for restore process."""

    total_files: int = 0
    extracted_files: int = 0
    total_size: int = 0
    extracted_size: int = 0
    skipped_files: int = 0
    errors: int = 0

    @property
    def progress_percent(self) -> float:
        """Calculate extraction progress as percentage.

        Returns:
            Progress in percent (0-100).
        """
        if self.total_files == 0:
            return 0.0
        return (self.extracted_files / self.total_files) * 100.0


class ArchiveOpener:
    """Opens ZIP archives with automatic password detection."""

    def __init__(self, archive_path: Path) -> None:
        """Initialize archive opener.

        Args:
            archive_path: Path to the ZIP archive.
        """
        self.archive_path = archive_path
        self._is_password_protected: Optional[bool] = None

    def is_password_protected(self) -> bool:
        """Check if archive is password protected.

        Returns:
            True if archive requires password, False otherwise.
        """
        if self._is_password_protected is not None:
            return self._is_password_protected

        try:
            with zipfile.ZipFile(self.archive_path, 'r') as archive:
                # Try to read the first file without password
                if archive.namelist():
                    try:
                        archive.read(archive.namelist()[0])
                        self._is_password_protected = False
                    except RuntimeError:
                        # RuntimeError usually means password required
                        self._is_password_protected = True
                else:
                    # Empty archive
                    self._is_password_protected = False
        except zipfile.BadZipFile:
            # Try with pyzipper for AES encryption
            try:
                import pyzipper  # type: ignore[import-untyped]
                with pyzipper.AESZipFile(self.archive_path, 'r') as archive:
                    if archive.namelist():
                        try:
                            archive.read(archive.namelist()[0])
                            self._is_password_protected = False
                        except RuntimeError:
                            self._is_password_protected = True
                    else:
                        self._is_password_protected = False
            except (ImportError, RuntimeError, zipfile.BadZipFile):
                # Assume password protected if we can't open it
                self._is_password_protected = True

        return self._is_password_protected

    def open_archive(self, password: Optional[bytes] = None) -> zipfile.ZipFile:
        """Open archive with optional password.

        Args:
            password: Optional password for encrypted archives.

        Returns:
            ZipFile object ready for extraction.

        Raises:
            zipfile.BadZipFile: If archive is corrupted.
            RuntimeError: If password is incorrect or required.
        """
        # Try standard zipfile first
        try:
            archive = zipfile.ZipFile(self.archive_path, 'r')
            if password:
                archive.setpassword(password)
            # Test if we can read the first file
            if archive.namelist():
                try:
                    archive.read(archive.namelist()[0], pwd=password)
                except RuntimeError:
                    # Password might be required, try pyzipper
                    archive.close()
                    raise RuntimeError("Password required or incorrect")
            return archive
        except (zipfile.BadZipFile, RuntimeError):
            # Try pyzipper for AES encryption
            try:
                import pyzipper  # type: ignore[import-untyped]
                archive = pyzipper.AESZipFile(self.archive_path, 'r')
                if password:
                    archive.setpassword(password)
                # Test if we can read the first file
                if archive.namelist():
                    archive.read(archive.namelist()[0])
                return archive
            except ImportError:
                raise RuntimeError(
                    "Archive appears to be encrypted. "
                    "Install pyzipper: pip install pyzipper"
                )
            except RuntimeError as e:
                if "Bad password" in str(e) or "password" in str(e).lower():
                    raise RuntimeError("Incorrect password")
                raise


class RestoreExtractor:
    """Extracts files from ZIP archive to target directory."""

    def __init__(
        self,
        archive_path: Path,
        target_dir: Path,
        password: Optional[bytes] = None,
        progress_callback: Optional[Callable[[RestoreStats], None]] = None
    ) -> None:
        """Initialize extractor.

        Args:
            archive_path: Path to ZIP archive.
            target_dir: Target directory for extraction.
            password: Optional password for encrypted archives.
            progress_callback: Optional callback for progress updates.
        """
        self.archive_path = archive_path
        self.target_dir = target_dir
        self.password = password
        self.progress_callback = progress_callback
        self.stats = RestoreStats()
        self.archive_opener = ArchiveOpener(archive_path)

    def validate_archive(self) -> None:
        """Validate archive file exists and is readable.

        Raises:
            FileNotFoundError: If archive does not exist.
            zipfile.BadZipFile: If archive is corrupted.
        """
        if not self.archive_path.exists():
            raise FileNotFoundError(
                f"Archive not found: {self.archive_path}"
            )

        if not self.archive_path.is_file():
            raise ValueError(
                f"Path is not a file: {self.archive_path}"
            )

        # Try to open and validate
        opener = ArchiveOpener(self.archive_path)
        try:
            with opener.open_archive(self.password) as archive:
                archive.testzip()
        except RuntimeError as e:
            if "password" in str(e).lower():
                raise RuntimeError("Password required or incorrect") from e
            raise
        except zipfile.BadZipFile as e:
            raise zipfile.BadZipFile(
                f"Archive is corrupted or not a valid ZIP file: {e}"
            ) from e

    def check_disk_space(self) -> None:
        """Check if there is enough disk space for extraction.

        Raises:
            OSError: If there is not enough disk space.
        """
        # Estimate required space (assume no compression for safety)
        archive_size = self.archive_path.stat().st_size
        target_drive = Path(self.target_dir.anchor) if self.target_dir.anchor else self.target_dir.parent

        if not target_drive.exists():
            return

        free_space = shutil.disk_usage(target_drive).free
        required_space = archive_size * 2  # Safety margin

        if free_space < required_space:
            raise OSError(
                f"Not enough disk space. Required: {format_size(required_space)}, "
                f"Available: {format_size(free_space)}"
            )

    def extract_archive(self) -> None:
        """Extract all files from archive to target directory.

        Raises:
            FileNotFoundError: If archive does not exist.
            zipfile.BadZipFile: If archive is corrupted.
            RuntimeError: If password is incorrect or required.
            OSError: If there are disk space or permission issues.
            KeyboardInterrupt: If extraction is interrupted by user.
        """
        self.validate_archive()
        self.check_disk_space()

        # Create target directory
        self.target_dir.mkdir(parents=True, exist_ok=True)

        archive: Optional[zipfile.ZipFile] = None
        try:
            archive = self.archive_opener.open_archive(self.password)

            # Get file list and calculate total size
            file_list = archive.namelist()
            self.stats.total_files = len(file_list)

            # Calculate total uncompressed size
            for file_info in archive.infolist():
                if not file_info.is_dir():
                    self.stats.total_size += file_info.file_size

            # Initial progress
            if self.progress_callback:
                self.progress_callback(self.stats)

            # Extract files
            for file_name in file_list:
                try:
                    file_info = archive.getinfo(file_name)

                    # Skip directories (they are created automatically)
                    if file_info.is_dir():
                        continue

                    # Calculate target path
                    target_path = self.target_dir / file_name

                    # Create parent directories
                    target_path.parent.mkdir(parents=True, exist_ok=True)

                    # Extract file
                    with archive.open(file_name, pwd=self.password) as source:
                        with target_path.open('wb') as target:
                            shutil.copyfileobj(source, target, length=CHUNK_SIZE)

                    # Update statistics
                    self.stats.extracted_files += 1
                    self.stats.extracted_size += file_info.file_size

                    # Update progress
                    if (self.stats.extracted_files % PROGRESS_UPDATE_INTERVAL == 0
                            or self.stats.extracted_files == self.stats.total_files):
                        if self.progress_callback:
                            self.progress_callback(self.stats)

                except (OSError, PermissionError) as e:
                    print(
                        f"Warning: Skipping {file_name}: {e}",
                        flush=True
                    )
                    self.stats.skipped_files += 1
                    self.stats.errors += 1
                    continue
                except RuntimeError as e:
                    if "password" in str(e).lower():
                        raise RuntimeError("Incorrect password") from e
                    raise

        except KeyboardInterrupt:
            print("\nExtraction interrupted by user.", flush=True)
            raise
        finally:
            if archive:
                archive.close()

        # Final progress
        if self.progress_callback:
            self.progress_callback(self.stats)


def format_size(size_bytes: int) -> str:
    """Format byte size into human-readable string.

    Args:
        size_bytes: Size in bytes.

    Returns:
        Formatted string with appropriate unit (B, KB, MB, GB, TB, PB).
    """
    for unit in ['B', 'KB', 'MB', 'GB', 'TB', 'PB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"


def get_password(max_attempts: int = 3) -> bytes:
    """Get password interactively from user with validation.

    Args:
        max_attempts: Maximum number of password attempts.

    Returns:
        Password as bytes (UTF-8 encoded).

    Raises:
        ValueError: If password is empty or max attempts exceeded.
        KeyboardInterrupt: If user cancels password entry.
    """
    print("\n" + "=" * 60, flush=True)
    print("ARCHIVE PASSWORD REQUIRED", flush=True)
    print("=" * 60, flush=True)

    for attempt in range(1, max_attempts + 1):
        try:
            password = getpass.getpass(f"Enter password (attempt {attempt}/{max_attempts}): ")

            if not password:
                print("Error: Password cannot be empty.", flush=True)
                continue

            return password.encode('utf-8')
        except KeyboardInterrupt:
            print("\nPassword entry cancelled by user.", flush=True)
            raise

    raise ValueError(f"Maximum password attempts ({max_attempts}) exceeded")


def verify_password(archive_path: Path, password: bytes) -> bool:
    """Verify password by attempting to open archive.

    Args:
        archive_path: Path to archive.
        password: Password to verify.

    Returns:
        True if password is correct, False otherwise.
    """
    opener = ArchiveOpener(archive_path)
    try:
        with opener.open_archive(password) as archive:
            # Try to read first file
            if archive.namelist():
                archive.read(archive.namelist()[0])
            return True
    except RuntimeError:
        return False
    except Exception:
        return False


def print_progress(stats: RestoreStats) -> None:
    """Print extraction progress.

    Args:
        stats: Restore statistics.
    """
    sys.stdout.write(
        f"\rExtracting: {stats.extracted_files}/{stats.total_files} files "
        f"({stats.progress_percent:.1f}%) - "
        f"{format_size(stats.extracted_size)}/{format_size(stats.total_size)}"
    )
    sys.stdout.flush()


def print_restore_info(stats: RestoreStats, target_dir: Path) -> None:
    """Print restore summary information.

    Args:
        stats: Restore statistics.
        target_dir: Target directory where files were extracted.
    """
    print("\n" + "=" * 60, flush=True)
    print("Restore complete!", flush=True)
    print(f"Target directory: {target_dir}", flush=True)
    print(f"Files extracted: {stats.extracted_files}/{stats.total_files}", flush=True)
    print(f"Total size extracted: {format_size(stats.extracted_size)}", flush=True)
    if stats.skipped_files > 0:
        print(f"Skipped files: {stats.skipped_files}", flush=True)
    if stats.errors > 0:
        print(f"Errors encountered: {stats.errors}", flush=True)
    print("=" * 60, flush=True)


def main() -> int:
    """Main entry point for restore script.

    Returns:
        Exit code: 0 for success, 1 for error.
    """
    setup_utf8_output()

    parser = argparse.ArgumentParser(
        description="Universal folder restore utility from ZIP backup."
    )
    parser.add_argument(
        "archive_path",
        type=Path,
        help="Path to the ZIP archive to restore from."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Target directory for extraction. "
             "Defaults to current directory with archive name."
    )
    parser.add_argument(
        "--password",
        type=str,
        default=None,
        help="Password for encrypted archive (not recommended for security). "
             "If not provided, will prompt interactively."
    )

    args = parser.parse_args()

    archive_path: Path = args.archive_path.resolve()

    if not archive_path.exists():
        print(f"ERROR: Archive not found: {archive_path}", flush=True)
        return 1

    # Determine target directory
    target_dir: Path
    if args.output:
        target_dir = args.output.resolve()
    else:
        # Default: current directory + archive name without extension
        target_dir = Path.cwd() / archive_path.stem

    print(f"Archive: {archive_path}", flush=True)
    print(f"Target directory: {target_dir}", flush=True)

    # Check if target directory exists and is not empty
    if target_dir.exists() and any(target_dir.iterdir()):
        print(
            f"WARNING: Target directory is not empty: {target_dir}",
            flush=True
        )
        response = input("Continue? (y/N): ").strip().lower()
        if response != 'y':
            print("Operation cancelled.", flush=True)
            return 0

    # Check if archive is password protected
    opener = ArchiveOpener(archive_path)
    password: Optional[bytes] = None

    if opener.is_password_protected():
        if args.password:
            password = args.password.encode('utf-8')
        else:
            try:
                password = get_password()
            except ValueError as e:
                print(f"ERROR: {e}", flush=True)
                return 1
            except KeyboardInterrupt:
                print("\n\nOperation cancelled by user.", flush=True)
                return 0

        # Verify password
        if not verify_password(archive_path, password):
            print("ERROR: Incorrect password.", flush=True)
            return 1

        print("✓ Password verified", flush=True)

    print("\n" + "=" * 60, flush=True)
    print("STARTING RESTORATION", flush=True)
    print("=" * 60, flush=True)
    print(f"Archive: {archive_path}", flush=True)
    print(f"Target: {target_dir}", flush=True)
    if password:
        print("Encryption: AES-256 (password protected)", flush=True)
    else:
        print("Encryption: NONE", flush=True)
    print("\nStarting extraction...", flush=True)

    extractor = RestoreExtractor(
        archive_path=archive_path,
        target_dir=target_dir,
        password=password,
        progress_callback=print_progress
    )

    try:
        extractor.extract_archive()
        print_restore_info(extractor.stats, target_dir)

        print("\n" + "=" * 60, flush=True)
        print("RESTORATION SUCCESSFULLY COMPLETED", flush=True)
        print("=" * 60, flush=True)
        print(f"Path: {target_dir}", flush=True)

    except KeyboardInterrupt:
        print("\n\nOperation interrupted by user.", flush=True)
        return 1
    except (FileNotFoundError, zipfile.BadZipFile, RuntimeError, OSError, ValueError) as e:
        print(f"\nERROR: {e}", flush=True)
        return 1
    except Exception as e:
        print(f"\nUNEXPECTED ERROR: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())

