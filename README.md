# Refplatinator

A tool to extract Cisco network device images from Cisco Reference Platform (refplat) files and build vrnetlab Docker images for network simulation.

## Overview

This tool automates the process of:
1. Extracting VM images from Cisco refplat ZIP and ISO files
2. Identifying and organizing images by platform type
3. Building vrnetlab Docker images for use in network simulation tools like ContainerLab

## Prerequisites

- Python 3.6+
- Docker (for building vrnetlab images)
- Git (for cloning vrnetlab repository)

## Installation

### Quick Install (curl | bash)

> **⚠️ CAUTION:** Piping scripts directly to bash can be dangerous. Always review the script before running it.
>
> View the install script first: https://raw.githubusercontent.com/torbbang/clab-refplatinator/main/install.sh

For a quick automated installation:

```bash
curl -fsSL https://raw.githubusercontent.com/torbbang/clab-refplatinator/main/install.sh | bash
```

Or to customize the installation directory:

```bash
INSTALL_DIR=/opt/refplatinator curl -fsSL https://raw.githubusercontent.com/torbbang/clab-refplatinator/main/install.sh | bash
```

### Manual Installation

1. Clone or download this repository:
   ```bash
   git clone https://github.com/torbbang/clab-refplatinator.git
   cd clab-refplatinator
   ```

2. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Usage

### Basic Usage

Place your Cisco refplat ZIP or ISO files in a directory called `refplats/`, then run:

```bash
python3 refplatinator.py
```

### Advanced Usage

```bash
# Specify custom directories
python3 refplatinator.py --source-dir /path/to/refplats --output-dir /path/to/output

# Enable verbose logging
python3 refplatinator.py --verbose

# Get help
python3 refplatinator.py --help
```

### Command Line Options

- `--source-dir`: Directory containing refplat ZIP/ISO files (default: `refplats`)
- `--output-dir`: Directory to extract images to (default: `refplat-images`)
- `--verbose`, `-v`: Enable verbose logging
- `--help`, `-h`: Show help message

## Supported Platforms

The tool supports extracting and building vrnetlab Docker images for these Cisco platforms:

### Currently Built Images
Based on the refplat files, the following images are successfully built:

- **ASAv** (`vrnetlab/cisco_asav:9-23-1`) - Cisco Adaptive Security Appliance Virtual
- **C8000V** (`vrnetlab/cisco_c8000v:17.16.01a`) - Cisco Catalyst 8000V Edge Platform
- **CAT9000V** (`vrnetlab/cisco_cat9kv:Q200_17_15_03`) - Cisco Catalyst 9000 Virtual Switch
- **Nexus 9000V** (`vrnetlab/cisco_n9kv:10_5_3_F`) - Cisco Nexus 9000V Virtual Switch
- **XRv9000** (`vrnetlab/cisco_xrv9k:25.1.1`) - Cisco IOS XRv9000 Virtual Router
- **IOL** (`vrnetlab/cisco_iol:XE_17_16_01A`) - IOS on Linux (L3)
- **IOL L2** (`vrnetlab/cisco_iol:L2-XE_17_16_01A`) - IOS on Linux (L2)
- **vIOS** (`vrnetlab/cisco_vios:159_3_M10`) - Virtual IOS Router
- **vIOS L2** (`vrnetlab/cisco_viosl2:2020`) - Virtual IOS Layer 2 Switch

### Platforms with vrnetlab Support (Not Yet Built)
These platforms are supported by vrnetlab but weren't found in the current refplat files:

- **CSR1000V** - Cisco Cloud Services Router 1000V
- **FTDv** - Cisco Secure Firewall Threat Defense Virtual
- **XRv** - Cisco IOS XRv Virtual Router
- **NX-OS** - Additional Nexus variants

### Not Supported (No vrnetlab Builder)
These platforms are extracted but require generic VM containers (not currently built):

- **ISE** - Cisco Identity Services Engine
- **FMC** - Secure Firewall Management Center
- **C9800-CL** - Cisco Catalyst 9800 Cloud Wireless Controller
- **Viptela vManage, vSmart, vBond** - SD-WAN Controllers

## How It Works

1. **Extraction**: The tool scans the source directory for refplat ZIP and ISO files
2. **Platform Detection**: Uses filename patterns to identify platform types and versions
3. **Image Processing**: Extracts VM images (QCOW2, IOL, etc.) from the refplat containers
4. **vrnetlab Integration**: Copies images to the appropriate vrnetlab platform directories
5. **Docker Build**: Executes `make docker-image` to build the vrnetlab containers

## Directory Structure

```
refplats/                    # Input refplat files
├── refplat-20250616-fcs.zip
├── refplat-20250718-ise.zip
└── ...

refplat-images/              # Extracted images (organized by refplat)
├── refplat-20250616-fcs/
│   ├── csr1000v-universalk9.17.03.08-serial.qcow2
│   └── ...
└── ...

vrnetlab/                    # vrnetlab repository (auto-cloned)
├── cisco/
│   ├── csr1000v/
│   ├── asav/
│   └── ...
└── ...
```

## Troubleshooting

### Common Issues

**"No module named 'pycdlib'"**
- Install dependencies: `pip install -r requirements.txt`

**"vrnetlab directory not found"**
- The tool automatically clones vrnetlab, ensure you have git and internet access

**"Build failed for platform X"**
- Check that Docker is running and you have sufficient disk space
- Some platforms may require specific image versions

**Temporary directories not cleaned up**
- The tool includes signal handlers for cleanup, but manual cleanup may be needed if forcefully terminated
- Remove any `tmp*` directories in the working directory

### Verbose Mode

Use `--verbose` to get detailed logging information for troubleshooting:

```bash
python3 refplatinator.py --verbose
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## Acknowledgments

- [vrnetlab](https://github.com/srl-labs/vrnetlab) - The container-based network lab platform
- [pycdlib](https://pycdlib.readthedocs.io/) - Pure Python ISO 9660 library
