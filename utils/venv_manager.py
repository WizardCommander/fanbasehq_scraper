#!/usr/bin/env python3
"""
Virtual Environment Management
Handles virtual environment detection, dependency checking, and script restart functionality.

Following CLAUDE.md best practices:
- C-4 (SHOULD): Prefer simple, composable, testable functions
- C-5 (MUST): Use branded types for IDs
- T-1 (MUST): Comprehensive unit tests in separate file
"""

import sys
import subprocess
import logging
from enum import Enum
from pathlib import Path
from typing import Optional, List


logger = logging.getLogger(__name__)


class VenvStatus(Enum):
    """Status of virtual environment detection"""

    ACTIVE = "active"
    INACTIVE = "inactive"
    NOT_FOUND = "not_found"


class VenvManager:
    """
    Manages virtual environment detection, dependency checking, and script restart.

    Decomposed from monolithic check_and_activate_venv() function for testability.
    Each method has a single responsibility and can be unit tested independently.
    """

    def __init__(self, project_root: Path):
        """
        Initialize VenvManager with project root directory.

        Args:
            project_root: Path to the project root directory

        Raises:
            ValueError: If project_root doesn't exist
        """
        if not project_root.exists():
            raise ValueError(f"Project root directory does not exist: {project_root}")

        self.project_root = project_root.resolve()

    def check_venv_status(self) -> VenvStatus:
        """
        Check if virtual environment is active, inactive, or not found.

        Returns:
            VenvStatus indicating current virtual environment state
        """
        # Check if we're already in a virtual environment
        if self._is_venv_active():
            return VenvStatus.ACTIVE

        # Check if venv directory exists
        venv_path = self.project_root / "venv"
        if not venv_path.exists():
            return VenvStatus.NOT_FOUND

        return VenvStatus.INACTIVE

    def _is_venv_active(self) -> bool:
        """
        Detect if Python is running in a virtual environment.

        Uses two detection methods:
        1. hasattr(sys, 'real_prefix') - virtualenv
        2. sys.base_prefix != sys.prefix - venv/pyvenv

        Returns:
            True if virtual environment is active
        """
        return hasattr(sys, "real_prefix") or (
            hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix
        )

    def get_venv_python_executable(self) -> Optional[Path]:
        """
        Find the Python executable in the virtual environment.

        Checks both Unix (bin/python) and Windows (Scripts/python.exe) paths.

        Returns:
            Path to Python executable, or None if not found
        """
        venv_path = self.project_root / "venv"

        # Try Unix path first
        python_unix = venv_path / "bin" / "python"
        if python_unix.exists():
            return python_unix

        # Try Windows path
        python_windows = venv_path / "Scripts" / "python.exe"
        if python_windows.exists():
            return python_windows

        return None

    def check_dependencies(self) -> bool:
        """
        Check if all requirements.txt dependencies are installed and up-to-date.

        Compares requirements.txt against installed packages using pip freeze.

        Returns:
            True if all dependencies are satisfied
        """
        requirements_file = self.project_root / "requirements.txt"
        if not requirements_file.exists():
            logger.warning("requirements.txt not found")
            return False

        python_exe = self.get_venv_python_executable()
        if not python_exe:
            logger.warning("Virtual environment Python executable not found")
            return False

        try:
            # Get installed packages
            result = subprocess.run(
                [str(python_exe), "-m", "pip", "freeze"],
                capture_output=True,
                text=True,
                check=True,
                cwd=self.project_root,
            )

            installed_packages = self._parse_pip_freeze_output(result.stdout)
            required_packages = self._parse_requirements_file(requirements_file)

            # Check if all required packages are installed
            for package, version_spec in required_packages.items():
                if package not in installed_packages:
                    logger.debug(f"Missing package: {package}")
                    return False

                # Basic version checking (could be enhanced for complex version specs)
                installed_version = installed_packages[package]
                if not self._version_satisfies(installed_version, version_spec):
                    logger.debug(
                        f"Package {package} version mismatch: installed {installed_version}, required {version_spec}"
                    )
                    return False

            return True

        except subprocess.CalledProcessError as e:
            logger.warning(f"Failed to check dependencies: {e}")
            return False

    def _parse_pip_freeze_output(self, freeze_output: str) -> dict:
        """
        Parse pip freeze output into package name -> version mapping.

        Args:
            freeze_output: Raw output from pip freeze command

        Returns:
            Dictionary mapping package names to installed versions
        """
        packages = {}
        for line in freeze_output.strip().split("\n"):
            if "==" in line:
                package, version = line.split("==", 1)
                packages[package.lower()] = version
        return packages

    def _parse_requirements_file(self, requirements_file: Path) -> dict:
        """
        Parse requirements.txt file into package name -> version spec mapping.

        Args:
            requirements_file: Path to requirements.txt file

        Returns:
            Dictionary mapping package names to version specifications
        """
        packages = {}
        for line in requirements_file.read_text().strip().split("\n"):
            line = line.strip()
            if line and not line.startswith("#"):
                # Simple parsing - could be enhanced for complex version specs
                if ">=" in line:
                    package, version = line.split(">=", 1)
                    packages[package.lower()] = f">={version}"
                elif "==" in line:
                    package, version = line.split("==", 1)
                    packages[package.lower()] = f"=={version}"
                else:
                    # Assume no version specified means any version
                    packages[line.lower()] = None
        return packages

    def _version_satisfies(
        self, installed_version: str, required_spec: Optional[str]
    ) -> bool:
        """
        Check if installed version satisfies requirement specification.

        Simple implementation - could be enhanced with packaging.specifiers for complex specs.

        Args:
            installed_version: Version string of installed package
            required_spec: Version specification (e.g., ">=1.0.0", "==2.1.0")

        Returns:
            True if installed version satisfies requirement
        """
        if required_spec is None:
            return True  # No version requirement

        if required_spec.startswith(">="):
            # Simple string comparison - could use packaging.version for proper comparison
            required_version = required_spec[2:]
            return installed_version >= required_version
        elif required_spec.startswith("=="):
            required_version = required_spec[2:]
            return installed_version == required_version

        # Default to satisfied for unknown specs
        return True

    def install_dependencies(self) -> bool:
        """
        Install dependencies from requirements.txt using virtual environment pip.

        Returns:
            True if installation succeeded
        """
        python_exe = self.get_venv_python_executable()
        if not python_exe:
            logger.error("Virtual environment Python executable not found")
            return False

        requirements_file = self.project_root / "requirements.txt"
        if not requirements_file.exists():
            logger.error("requirements.txt not found")
            return False

        try:
            logger.info("Installing dependencies from requirements.txt...")
            subprocess.run(
                [str(python_exe), "-m", "pip", "install", "-r", str(requirements_file)],
                check=True,
                capture_output=True,
                text=True,
                cwd=self.project_root,
            )
            logger.info("Dependencies installed successfully")
            return True

        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to install dependencies: {e}")
            return False

    def restart_with_venv(self) -> None:
        """
        Restart the current script using the virtual environment Python executable.

        Uses subprocess.run with validated arguments to prevent injection attacks.
        Exits the current process after successful restart.

        Raises:
            RuntimeError: If restart fails
        """
        python_exe = self.get_venv_python_executable()
        if not python_exe:
            raise RuntimeError("Virtual environment Python executable not found")

        # Validate python executable path for security
        if not self._is_safe_python_executable(python_exe):
            raise RuntimeError(f"Invalid Python executable path: {python_exe}")

        try:
            logger.info("Restarting script with virtual environment...")

            # Build command with validated arguments
            cmd = [str(python_exe)] + sys.argv

            # Execute with explicit working directory
            result = subprocess.run(cmd, cwd=self.project_root)

            # Exit with the same return code
            sys.exit(result.returncode)

        except Exception as e:
            raise RuntimeError(
                f"Failed to restart script with virtual environment: {e}"
            )

    def _is_safe_python_executable(self, python_exe: Path) -> bool:
        """
        Validate Python executable path for security.

        Ensures the executable is within the expected venv directory
        and has the expected name to prevent subprocess injection.

        Args:
            python_exe: Path to Python executable

        Returns:
            True if path is safe to execute
        """
        try:
            # Must be absolute path
            if not python_exe.is_absolute():
                return False

            # Must be within project venv directory
            venv_path = self.project_root / "venv"
            if not str(python_exe).startswith(str(venv_path)):
                return False

            # Must have expected name
            if python_exe.name not in ["python", "python.exe"]:
                return False

            return True

        except Exception:
            return False

    def ensure_venv_ready(self) -> bool:
        """
        Main entry point: ensure virtual environment is ready and active.

        Handles all cases:
        1. Already active -> return True
        2. Not found -> warn and continue
        3. Inactive -> check dependencies, install if needed, restart

        Returns:
            True if environment is ready (or user chooses to continue without venv)

        Raises:
            RuntimeError: If dependency installation fails or restart fails
        """
        status = self.check_venv_status()

        if status == VenvStatus.ACTIVE:
            logger.debug("Virtual environment is already active")
            return True

        elif status == VenvStatus.NOT_FOUND:
            self._print_venv_not_found_warning()
            return True  # Continue execution without venv

        elif status == VenvStatus.INACTIVE:
            logger.info("Virtual environment detected but not active")

            # Check if dependencies need updating
            if not self.check_dependencies():
                logger.info("Dependencies need updating...")
                if not self.install_dependencies():
                    raise RuntimeError("Failed to install dependencies")

            # Restart with virtual environment
            self.restart_with_venv()
            # This function never returns (process exits in restart_with_venv)

        return True

    def _print_venv_not_found_warning(self) -> None:
        """Print user-friendly warning when virtual environment is not found."""
        print("WARNING: Virtual environment not found at 'venv/'")
        print("   This may cause dependency issues. To set up venv:")
        print(
            "   python -m venv venv && source venv/bin/activate && pip install -r requirements.txt"
        )
        print("   Continuing anyway...")
