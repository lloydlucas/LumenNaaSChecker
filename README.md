# LumenNaaSChecker

## Overview
LumenNaaSChecker is a tool designed to check and validate Network-as-a-Service (NaaS) configurations and deployments for Lumen networks. It helps automate the process of verifying network setups, ensuring compliance and operational readiness.

## Features
- Automated NaaS configuration validation
- Reporting and logging of issues
- Extensible for custom checks

## Requirements
- Python 3.8+
- Any additional dependencies (see requirements.txt)

## Installation
1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/LumenNaaSChecker.git
   ```
2. Navigate to the project directory:
   ```bash
   cd LumenNaaSChecker
   ```
3. (Optional) Create and activate a virtual environment:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```
4. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Usage
Run the main checker script:
```bash
python main.py
```


## Environment Variables
The following environment variables must be set in a `.env` file in the project root:

| Variable              | Description                                      |
|-----------------------|--------------------------------------------------|
| USERNAME              | OAuth username for Lumen API                     |
| SECRET                | OAuth secret for Lumen API                       |
| CUSTOMER_NUMBER       | Your Lumen customer number                       |
| SERVICE_ID            | The service ID to check inventory for            |
| CURRENCY_CODE         | Currency code (e.g., USD)                        |
| PARTNER_ID            | Lumen partner ID                                 |
| PRODUCT_CODE          | Product code (e.g., 718)                         |
| PRODUCT_NAME          | Product name (e.g., Internet On-Demand)          |
| EXTERNAL_ID_PREFIX    | Prefix for external order IDs                    |
| CONTACT_NAME          | Contact name for order requests                  |
| CONTACT_ROLE          | Contact role for order requests                  |
| CONTACT_EMAIL         | Contact email for order requests                 |
| CONTACT_ORG           | Contact organization for order requests          |
| CONTACT_PHONE         | Contact phone number for order requests          |
| BANDWIDTH_FULL        | Bandwidth value for full access (e.g., 1 mbps)   |
| BANDWIDTH_HEARTBEAT   | Bandwidth value for heartbeat (e.g., 1 mbps)     |
| LUMEN_IP              | Lumen IP address for bandwidth comparison        |

These variables are required for authentication, API requests, and order placement. See the code for additional optional variables.

## Contributing
Contributions are welcome! Please fork the repository and submit a pull request. For major changes, open an issue first to discuss what you would like to change.

## License
This project is licensed under the MIT License.

## Contact
For questions or support, contact [your.email@example.com](mailto:your.email@example.com).
