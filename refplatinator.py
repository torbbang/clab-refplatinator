import os
import zipfile
import subprocess
import tempfile
from pathlib import Path
import pycdlib
import pycdlib.pycdlibexception
import logging
import sys
import signal
import atexit
import shutil
import argparse

# Global registry for cleanup
_temp_directories = []

def _cleanup_temp_directories():
    """Clean up any registered temporary directories."""
    for temp_dir in _temp_directories[:]:
        if temp_dir.exists():
            try:
                shutil.rmtree(temp_dir)
                print(f"Cleaned up temporary directory: {temp_dir}")
                _temp_directories.remove(temp_dir)
            except Exception as e:
                print(f"Failed to cleanup temp directory {temp_dir}: {e}")

def _signal_handler(signum, frame):
    """Handle signals by cleaning up and exiting."""
    print(f"Received signal {signum}, cleaning up temporary directories...")
    _cleanup_temp_directories()
    sys.exit(1)

# Register cleanup functions
atexit.register(_cleanup_temp_directories)
signal.signal(signal.SIGINT, _signal_handler)
signal.signal(signal.SIGTERM, _signal_handler)

def setup_logging(verbose=False):
    """Configure logging based on verbosity level."""
    level = logging.DEBUG if verbose else logging.INFO
    format_str = '%(levelname)s: %(message)s'
    if verbose:
        format_str = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

    logging.basicConfig(
        level=level,
        format=format_str,
        handlers=[logging.StreamHandler(sys.stdout)]
    )
    return logging.getLogger(__name__)

def extract_images_from_refplats(source_dir="refplats", output_dir="refplat-images", vrnetlab_dir="vrnetlab"):
    refplats_dir = Path(source_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(exist_ok=True)

    # Get list of supported platforms from vrnetlab
    vrnetlab_path = Path(vrnetlab_dir)
    if not vrnetlab_path.exists():
        print(f"Cloning vrnetlab repository...")
        subprocess.run([
            "git", "clone", "https://github.com/srl-labs/vrnetlab.git", str(vrnetlab_path)
        ], check=True)

    supported_platforms = set()
    cisco_dir = vrnetlab_path / "cisco"
    if cisco_dir.exists():
        for platform_dir in cisco_dir.iterdir():
            if platform_dir.is_dir():
                supported_platforms.add(platform_dir.name)

    # Add generic_vm for platforms not directly supported by vrnetlab
    supported_platforms.add('generic_vm')

    print(f"Found {len(supported_platforms)} supported platforms: {', '.join(sorted(supported_platforms))}")

    for refplat_file in refplats_dir.glob("*"):
        if refplat_file.suffix.lower() == ".zip":
            extract_from_zip(refplat_file, output_dir, supported_platforms)
        elif refplat_file.suffix.lower() == ".iso":
            extract_from_iso(refplat_file, output_dir, supported_platforms)

def extract_from_zip(zip_file, output_dir, supported_platforms):
    print(f"Extracting from ZIP: {zip_file}")
    with zipfile.ZipFile(zip_file, 'r') as zip_ref:
        with tempfile.TemporaryDirectory(dir=".") as temp_dir:
            temp_path = Path(temp_dir)

            # Register for cleanup in case of interruption
            _temp_directories.append(temp_path)

            try:
                zip_ref.extractall(temp_dir)
                iso_files = list(temp_path.rglob("*.iso"))
                print(f"Found {len(iso_files)} ISO files in ZIP")

                for iso_file in iso_files:
                    try:
                        extract_from_iso(iso_file, output_dir, supported_platforms)
                    except Exception as e:
                        print(f"Error processing ISO {iso_file}: {e}")

            except Exception as e:
                print(f"Error in extract_from_zip: {e}")
                raise

        # Unregister from cleanup list since it was cleaned up normally
        if temp_path in _temp_directories:
            _temp_directories.remove(temp_path)

def should_extract_file(filename, supported_platforms, platform_patterns):
    """Check if a file should be extracted based on supported platforms."""
    filename_clean = filename.replace(';1', '').lower()

    for platform_config in platform_patterns:
        platform = platform_config['platform']
        pattern = platform_config['pattern']

        if platform in supported_platforms and re.match(pattern, filename_clean):
            return True

    return False

def extract_from_iso(iso_file, output_dir, supported_platforms):
    file_output_dir = output_dir / iso_file.stem
    file_output_dir.mkdir(exist_ok=True)

    def patch_rock_ridge_for_multiple_er():
        """Temporarily patch pycdlib to handle multiple ER records."""
        import pycdlib.rockridge

        # Store original has_entry method
        original_has_entry = pycdlib.rockridge.RockRidge.has_entry

        def patched_has_entry(self, name):
            # Skip the check for ER records to allow multiple ER records
            if name == 'er_record':
                return False
            return original_has_entry(self, name)

        # Apply patch
        pycdlib.rockridge.RockRidge.has_entry = patched_has_entry
        return original_has_entry

    def restore_rock_ridge_method(original_method):
        """Restore the original has_entry method."""
        import pycdlib.rockridge
        pycdlib.rockridge.RockRidge.has_entry = original_method

    # Try using pycdlib with multiple ER record support
    original_method = patch_rock_ridge_for_multiple_er()

    try:
        iso = pycdlib.PyCdlib()
        iso.open(str(iso_file))

        extracted_files = {}  # Track extracted files by filename -> {path, size}

        # Determine which path type to use (prefer Joliet for full filenames)
        use_joliet = iso.joliet_vd is not None
        path_type = 'joliet_path' if use_joliet else 'iso_path'
        path_kwargs = {path_type: '/'}
        dir_pattern = '/virl-base-images/' if use_joliet else '/VIRL_BASE_IMAGES/'

        # First pass: collect all files and their sizes
        for dirname, dirlist, filelist in iso.walk(**path_kwargs):
            if dir_pattern in dirname:
                for filename in filelist:
                    if any(ext in filename.upper() for ext in ['.QCOW2', '.IMG', '.IOL']):
                        # Check if we should extract this file based on supported platforms
                        if not should_extract_file(filename, supported_platforms, PLATFORM_PATTERNS):
                            continue
                        iso_path = dirname + '/' + filename if dirname != '/' else '/' + filename
                        file_lower = filename.lower()

                        # Get file size to determine which version to use
                        try:
                            entry = iso.get_entry(iso_path, joliet=use_joliet)
                            file_size = entry.data_length
                        except:
                            file_size = 0

                        # If we haven't seen this file, or this version is larger, use it
                        if file_lower not in extracted_files or file_size > extracted_files[file_lower]['size']:
                            extracted_files[file_lower] = {'path': iso_path, 'size': file_size}

        # Second pass: extract files
        for filename, file_info in extracted_files.items():
            iso_path = file_info['path']
            file_size = file_info['size']
            # Remove ISO version suffix (;1) from filename
            clean_filename = filename.replace(';1', '')
            output_path = file_output_dir / clean_filename

            print(f"  Extracting {clean_filename} ({file_size} bytes) from {iso_path}")

            # Skip files with zero size
            if file_size == 0:
                print(f"    Skipping {filename} (zero bytes)")
                continue

            iso.get_file_from_iso(str(output_path), **{path_type: iso_path})

            # Store the original ISO folder name for version extraction
            iso_folder_name = iso_path.split('/')[-2] if '/' in iso_path else ''
            version_info_file = output_path.with_suffix('.version_info')
            with open(version_info_file, 'w') as f:
                f.write(iso_folder_name)

            # For CAT9KV, also extract vswitch.xml from node definition
            if 'cat9kv' in filename:
                extract_vswitch_xml(iso, file_output_dir)

        iso.close()

    finally:
        # Always restore the original method
        restore_rock_ridge_method(original_method)


def extract_vswitch_xml(iso, output_dir):
    """Extract vswitch.xml content from CAT9000V UADP node definition."""
    try:
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w+b', delete=False, dir=".") as temp_file:
            temp_path = temp_file.name

        iso.get_file_from_iso(temp_path, iso_path='/NODE_DEFINITIONS/CAT9000V_UADP.YAML')

        with open(temp_path, 'r', encoding='utf-8') as f:
            yaml_content = f.read()

        import os
        os.unlink(temp_path)

        # Extract vswitch.xml content from YAML
        import re
        vswitch_match = re.search(r'name: conf/vswitch\.xml\s+content: \|-\s+(.*?)(?=\s+editable:)',
                                 yaml_content, re.DOTALL)

        if vswitch_match:
            vswitch_content = vswitch_match.group(1)
            # Clean up YAML indentation (remove leading spaces)
            lines = vswitch_content.split('\n')
            cleaned_lines = []
            for line in lines:
                if line.strip():  # Skip empty lines
                    # Remove consistent leading whitespace (10 spaces from YAML)
                    if line.startswith('          '):
                        cleaned_lines.append(line[10:])
                    else:
                        cleaned_lines.append(line.lstrip())

            vswitch_xml = '\n'.join(cleaned_lines)

            # Write vswitch.xml file
            with open(output_dir / 'vswitch.xml', 'w') as f:
                f.write(vswitch_xml)

            print(f"  Extracted vswitch.xml for CAT9KV UADP")

    except Exception as e:
        print(f"  Warning: Could not extract vswitch.xml: {e}")


import re

# Platform mappings based on filename patterns
PLATFORM_PATTERNS = [
        # Cisco ASAv - extract version like 9.23.1 from asav9_23_1.qcow2
        {
            'pattern': r'^asav(\d+)_(\d+)_(\d+)\.qcow2$',
            'platform': 'asav',
            'rename_format': 'asav{major}-{minor}-{patch}.qcow2',
            'version_extract': lambda m: {'major': m.group(1), 'minor': m.group(2), 'patch': m.group(3)}
        },
        # Cisco CAT9000V
        {
            'pattern': r'^cat9kv.*\.qcow2$',
            'platform': 'cat9kv',
            'rename_format': 'cat9kv_prd-{version}.qcow2'
        },
        # Cisco Nexus 9000V
        {
            'pattern': r'^nexus9300v.*\.qcow2$',
            'platform': 'n9kv',
            'rename_format': 'n9kv-{version}.qcow2'
        },
        # Cisco IOS XRv9000 - extract version like 25.1.1 from xrv9k_fullk9_x_25_1_1.qcow2
        {
            'pattern': r'^xrv9k_fullk9_x_(\d+)_(\d+)_(\d+)\.qcow2$',
            'platform': 'xrv9k',
            'rename_format': 'xrv9k-fullk9-x-{major}.{minor}.{patch}.qcow2',
            'version_extract': lambda m: {'major': m.group(1), 'minor': m.group(2), 'patch': m.group(3)}
        },
        # Cisco CSR1000V
        {
            'pattern': r'^csr1000v.*\.qcow2$',
            'platform': 'csr1000v',
            'rename_format': 'csr1000v-universalk9.{version}-serial.qcow2'
        },
        # Cisco C8000V (Catalyst 8000V) - convert 17_16_01A to 17.16.01a
        {
            'pattern': r'^c8000v_universalk9.*\.qco$',
            'platform': 'c8000v',
            'rename_format': 'c8000v-{version}.qcow2',
            'version_transform': lambda v: v.replace('_', '.').lower() if '_' in v else v
        },
        # Cisco IOL (L3)
        {
            'pattern': r'^x86_64_crb_linux_adventerpr.*\.iol$',
            'platform': 'iol',
            'rename_format': 'cisco_iol-{version}.bin'
        },
        # Cisco IOL L2
        {
            'pattern': r'^x86_64_crb_linux_l2.*\.iol$',
            'platform': 'iol',
            'rename_format': 'cisco_iol-L2-{version}.bin'
        },
        # Cisco ISE
        {
            'pattern': r'^cisco_vise.*\.qcow2$',
            'platform': 'ise',
            'rename_format': 'cisco-ise-{version}.qcow2'
        },
        # Cisco IOSv (vIOS Layer 3)
        {
            'pattern': r'^vios_adventerprisek9_m_spa.*\.qco$',
            'platform': 'vios',
            'rename_format': 'cisco_vios-{version}.qcow2'
        },
        # Cisco IOSvL2 (vIOS Layer 2)
        {
            'pattern': r'^vios_l2_adventerprisek9_m_s.*\.qco$',
            'platform': 'viosl2',
            'rename_format': 'cisco_viosl2-{version}.qcow2'
        },
        # Cisco ISE (as generic VM)
        {
            'pattern': r'^cisco_vise.*\.qcow2$',
            'platform': 'generic_vm',
            'rename_format': 'cisco_ise-{version}.qcow2'
        },
        # Cisco Secure Firewall Threat Defense (FTDv) - convert 7_7_0 to 7.7.0-1
        {
            'pattern': r'^cisco_secure_firewall_threa.*\.qco$',
            'platform': 'ftdv',
            'rename_format': 'Cisco_Secure_Firewall_Threat_Defense_Virtual-{version}-1.qcow2',
            'version_transform': lambda v: v.replace('_', '.') if '_' in v else v
        },
        # Cisco Secure Firewall Management Center
        {
            'pattern': r'^cisco_secure_fw_mgmt_center.*\.qco$',
            'platform': 'generic_vm',
            'rename_format': 'cisco_fmc-{version}.qcow2'
        },
        # Cisco C9800-CL Wireless Controller
        {
            'pattern': r'^c9800_cl_universalk9.*\.qco$',
            'platform': 'generic_vm',
            'rename_format': 'cisco_c9800cl-{version}.qcow2'
        }
]

def build_vrnetlab_images(extracted_images_dir="refplat-images", vrnetlab_dir="vrnetlab"):
    """Build vrnetlab docker images from extracted refplat images."""

    def extract_version_from_folder(folder_name):
        """Extract version from refplat folder name."""
        clean_name = folder_name.replace('refplat-', '')

        # Look for version patterns
        version_patterns = [
            r'(\d{8})',  # YYYYMMDD format
            r'(\d+\.\d+\.\d+)',  # x.y.z format
            r'(\d+\.\d+)',  # x.y format
        ]

        for pattern in version_patterns:
            match = re.search(pattern, clean_name)
            if match:
                return match.group(1)

        return clean_name

    def match_image_to_platform(image_file, folder_version):
        """Match an image file to a platform configuration."""
        filename = image_file.name.replace(';1', '')  # Remove ISO version suffix

        for platform_config in PLATFORM_PATTERNS:
            match = re.match(platform_config['pattern'], filename)
            if match:
                # Check if platform has custom version extraction
                if 'version_extract' in platform_config:
                    version_parts = platform_config['version_extract'](match)
                    rename_to = platform_config['rename_format'].format(**version_parts)
                    version = f"{version_parts.get('major', '')}.{version_parts.get('minor', '')}.{version_parts.get('patch', '')}"
                else:
                    # Apply version transformation if specified
                    if 'version_transform' in platform_config:
                        version = platform_config['version_transform'](folder_version)
                    else:
                        version = folder_version

                    rename_to = platform_config['rename_format'].format(version=version)

                return {
                    'platform': platform_config['platform'],
                    'rename_to': rename_to,
                    'version': version
                }

        return None

    extracted_dir = Path(extracted_images_dir)
    vrnetlab_path = Path(vrnetlab_dir)

    if not vrnetlab_path.exists():
        print(f"Cloning vrnetlab repository...")
        subprocess.run([
            "git", "clone", "https://github.com/srl-labs/vrnetlab.git", str(vrnetlab_path)
        ], check=True)

    built_images = []

    # Process each refplat directory
    for refplat_dir in extracted_dir.iterdir():
        if not refplat_dir.is_dir():
            continue

        folder_version = extract_version_from_folder(refplat_dir.name)
        print(f"\nProcessing {refplat_dir.name} (version: {folder_version})...")

        for image_file in refplat_dir.iterdir():
            if not image_file.is_file():
                continue

            # Skip .version_info files and other non-image files
            if image_file.suffix == '.version_info' or image_file.name.endswith('.yaml'):
                continue

            if image_file.stat().st_size == 0:
                print(f"  Skipping {image_file.name} (zero bytes)")
                continue

            # Try to get version from the stored ISO folder name
            version_info_file = image_file.with_suffix('.version_info')
            if version_info_file.exists():
                with open(version_info_file, 'r') as f:
                    iso_folder_name = f.read().strip()
                    # Extract version from ISO folder name like IOSV_159_3_M10 -> 159_3_M10
                    if '_' in iso_folder_name:
                        version_from_folder = '_'.join(iso_folder_name.split('_')[1:])
                    else:
                        version_from_folder = folder_version
            else:
                version_from_folder = folder_version

            mapping = match_image_to_platform(image_file, version_from_folder)

            if not mapping:
                # Silently skip files we can't map instead of cluttering output
                continue

            platform = mapping['platform']
            new_name = mapping['rename_to']
            version = mapping['version']

            # Handle generic VMs differently (no vrnetlab build)
            if platform == 'generic_vm':
                print(f"  Creating {platform} image: {new_name}")
                target_dir = Path(extracted_images_dir) / "generic_vms"
                target_dir.mkdir(exist_ok=True)

                import shutil
                output_path = target_dir / new_name
                shutil.copy2(image_file, output_path)
                print(f"  ✓ Copied to: {output_path}")
                continue

            platform_dir = vrnetlab_path / "cisco" / platform

            if not platform_dir.exists():
                # Silently skip platforms not found in vrnetlab
                continue

            target_file = platform_dir / new_name

            print(f"  Building cisco/{platform}:{version} from {image_file.name}...")

            import shutil
            shutil.copy2(image_file, target_file)

            # For CAT9KV, also copy vswitch.xml if it exists
            if platform == 'cat9kv':
                vswitch_file = image_file.parent / 'vswitch.xml'
                if vswitch_file.exists():
                    shutil.copy2(vswitch_file, platform_dir / 'vswitch.xml')
                    print(f"    Copied vswitch.xml for UADP configuration")

            try:
                result = subprocess.run([
                    "make", "docker-image"
                ], cwd=platform_dir, capture_output=True, text=True, check=True)


                # Look for Docker image name in build output
                lines = result.stdout.split('\n') + result.stderr.split('\n')
                image_name = None
                for line in lines:
                    if 'Successfully tagged' in line:
                        image_name = line.split()[-1]
                        break
                    elif 'naming to docker.io/' in line:
                        # Alternative pattern for newer Docker output
                        image_name = line.split('naming to docker.io/')[-1].strip()
                        break

                if image_name:
                    # Clean up the image name to remove extra Docker output
                    image_name = image_name.split()[0]  # Remove any trailing text
                    built_images.append(image_name)
                    print(f"  ✓ Built: {image_name}")
                else:
                    # If we can't parse the image name, construct it from platform/version
                    expected_image = f"vrnetlab/cisco_{platform}:{version}"
                    built_images.append(expected_image)
                    print(f"  ✓ Built: {expected_image}")

                # Only clean up on success
                if target_file.exists():
                    target_file.unlink()
                if platform == 'cat9kv':
                    vswitch_cleanup = platform_dir / 'vswitch.xml'
                    if vswitch_cleanup.exists():
                        vswitch_cleanup.unlink()

            except subprocess.CalledProcessError as e:
                print(f"  ✗ Build failed: {e}")
                if e.stderr:
                    print(f"    Error output: {e.stderr.strip()}")
                # Don't clean up files on failure so user can debug

    print(f"\nBuild complete! Built {len(built_images)} images:")
    for image in built_images:
        print(f"  - {image}")

    return built_images

def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Extract Cisco network device images from refplat files and build vrnetlab Docker images.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 refplat-inator.py
  python3 refplat-inator.py --source-dir /path/to/refplats --output-dir /path/to/output
  python3 refplat-inator.py --verbose
        """
    )
    parser.add_argument(
        '--source-dir',
        default='refplats',
        help='Directory containing refplat ZIP/ISO files (default: refplats)'
    )
    parser.add_argument(
        '--output-dir',
        default='refplat-images',
        help='Directory to extract images to (default: refplat-images)'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging'
    )
    return parser.parse_args()

def main():
    args = parse_args()
    logger = setup_logging(args.verbose)

    try:
        extract_images_from_refplats(args.source_dir, args.output_dir)
        build_vrnetlab_images(args.output_dir)
    except KeyboardInterrupt:
        print("Operation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()