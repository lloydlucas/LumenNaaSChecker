import subprocess
import os
from dotenv import load_dotenv
import requests
import base64
import time

base_url = "https://api.lumen.com"

def get_egress_ip():
	"""
	Retrieve the current egress IP address and persist it to .env as EGRESS_IP.
	
	Returns the IP address string, or None on failure.
	"""
	try:
		result = subprocess.run(['curl', '-s', 'ifconfig.me'], capture_output=True, text=True)
		egress_ip = result.stdout.strip()
		if not egress_ip:
			raise ValueError("No IP returned from ifconfig.me")
		
		print(f"{egress_ip}")
		_update_env_file({'EGRESS_IP': egress_ip})
		os.environ['EGRESS_IP'] = egress_ip
		return egress_ip
	except Exception as e:
		print(f"Failed to get egress IP: {e}")
		return None

def _update_env_file(updates: dict) -> None:
	"""Update or append keys in the local .env file.

	This is intentionally simple: it preserves the existing file layout and comments,
	replacing any lines that start with a key that's present in `updates`, and appending
	any keys not already present.
	"""
	env_path = '.env'
	lines = []
	if os.path.exists(env_path):
		with open(env_path, 'r') as f:
			lines = f.readlines()

	out_lines = []
	replaced = set()
	for line in lines:
		stripped = line.strip()
		if not stripped or stripped.startswith('#') or '=' not in line:
			out_lines.append(line)
			continue
		key = line.split('=', 1)[0]
		if key in updates:
			out_lines.append(f"{key}={updates[key]}\n")
			replaced.add(key)
		else:
			out_lines.append(line)

	for k, v in updates.items():
		if k not in replaced:
			out_lines.append(f"{k}={v}\n")

	with open(env_path, 'w') as f:
		f.writelines(out_lines)


def get_access_token(force: bool = False) -> str:
	"""
	Return a valid access token.

	If `force` is False the cached token is returned when present and not expired. When a new
	token is requested it is written to `.env` along with `ACCESS_TOKEN_EXPIRES_AT` (epoch secs)
	and the local environment variables are updated.
	
	Raises ValueError on failure to obtain a token.
	"""
	load_dotenv()
	if not force:
		token = os.getenv('ACCESS_TOKEN')
		if token and not is_access_token_expired():
			return token

	username = os.getenv('USERNAME')
	secret = os.getenv('SECRET')
	if not username or not secret:
		raise ValueError("USERNAME and SECRET must be set in .env file.")

	url = f"{base_url}/oauth/v2/token"
	payload = 'grant_type=client_credentials'
	basic_auth = base64.b64encode(f"{username}:{secret}".encode()).decode()
	headers = {
		'Content-Type': 'application/x-www-form-urlencoded',
		'Authorization': f"Basic {basic_auth}"
	}

	response = requests.post(url, headers=headers, data=payload)
	if response.status_code != 200:
		raise ValueError(f"Failed to get token: {response.status_code} {response.text}")

	data = response.json()
	access_token = data.get('access_token')
	expires_in = data.get('expires_in')
	if not access_token:
		raise ValueError("No access token found in response.")

	updates = {'ACCESS_TOKEN': access_token}
	if expires_in is not None:
		try:
			expires_at = int(time.time()) + int(expires_in)
			updates['ACCESS_TOKEN_EXPIRES_AT'] = str(expires_at)
		except Exception:
			# ignore expiry if parsing fails
			pass

	# write and update in-memory env for immediate use
	_update_env_file(updates)
	os.environ['ACCESS_TOKEN'] = access_token
	if 'ACCESS_TOKEN_EXPIRES_AT' in updates:
		os.environ['ACCESS_TOKEN_EXPIRES_AT'] = updates['ACCESS_TOKEN_EXPIRES_AT']

	print(f"ACCESS_TOKEN updated (expires_in={expires_in})")
	return access_token


def is_access_token_expired(buffer_seconds: int = 60) -> bool:
	"""Return True if the stored access token is missing or will expire within buffer_seconds."""
	load_dotenv()
	expires_at = os.getenv('ACCESS_TOKEN_EXPIRES_AT')
	if not expires_at:
		return True
	try:
		expires_at_i = int(expires_at)
		return expires_at_i <= int(time.time()) + int(buffer_seconds)
	except Exception:
		# if parsing fails, treat as expired
		return True


def get_valid_access_token(buffer_seconds: int = 60) -> str:
	"""Return a valid access token, refreshing it if missing/expired."""
	load_dotenv()
	token = os.getenv('ACCESS_TOKEN')
	if token and not is_access_token_expired(buffer_seconds):
		return token
	# refresh
	new = get_access_token()
	if not new:
		raise ValueError("Failed to obtain access token")
	return new

def check_inventory(service_id: str = None, page_number: int = 1, page_size: int = 10, naas_enabled: bool = True, entitled: bool = True, service_type: str = "Internet", access_token: str = None):
    """
    Check Lumen product inventory for a given service.

    Values pulled from .env when not provided:
    - CUSTOMER_NUMBER -> header 'x-customer-number'
    - SERVICE_ID -> used as serviceId query param when service_id not provided
    - ACCESS_TOKEN -> Bearer token (will auto-refresh if missing)

    Returns parsed JSON response with extracted bandwidth in data['_bandwidth'].
    """
    load_dotenv()

    customer_number = os.getenv('CUSTOMER_NUMBER')
    if not customer_number:
        raise ValueError("CUSTOMER_NUMBER must be set in .env file.")

    service_id = service_id or os.getenv('SERVICE_ID')
    if not service_id:
        raise ValueError("service_id parameter or SERVICE_ID in .env must be provided.")

    access_token = access_token or get_valid_access_token()

    url = f"{base_url}/ProductInventory/v1/inventory"
    headers = {
        'x-customer-number': customer_number,
        'Authorization': f'Bearer {access_token}'
    }
    params = {
        'pageNumber': page_number,
        'pageSize': page_size,
        'naasEnabled': str(naas_enabled).lower(),
        'entitled': str(entitled).lower(),
        'serviceType': service_type,
        'serviceId': service_id
    }

    resp = requests.get(url, headers=headers, params=params)
    try:
        resp.raise_for_status()
    except requests.HTTPError:
        print(f"Inventory request failed: {resp.status_code} {resp.text}")
        raise

    try:
        data = resp.json()
    except ValueError:
        print(resp.text)
        return resp.text

    # Extract and persist data from first service inventory
    service_inventory = data.get('serviceInventory', []) if isinstance(data, dict) else []
    if service_inventory:
        svc = service_inventory[0]
        env_updates = {}

        # Extract master site ID (support both key variations)
        loc = svc.get('location') or {}
        master_siteid = loc.get('masterSiteid') or loc.get('masterSiteId')
        if master_siteid:
            env_updates['MASTER_SITE_ID'] = master_siteid

        # Extract billing account
        billing = svc.get('billingAccount') or {}
        if billing.get('id'):
            env_updates['BILLING_ACCOUNT_ID'] = billing['id']
        if billing.get('name'):
            env_updates['BILLING_ACCOUNT_NAME'] = billing['name']

    return data



def set_quote_bandwidth():
	"""
	Determine quote bandwidth based on egress IP comparison.
	
	Reads EGRESS_IP from .env and compares with LUMEN_IP:
	- If same: set QUOTE_BANDWIDTH = BANDWIDTH_FULL
	- If different: set QUOTE_BANDWIDTH = BANDWIDTH_HEARTBEAT
	
	Returns the bandwidth value set.
	"""
	load_dotenv()

	# Ensure we have an egress IP; if not, attempt to retrieve it
	egress_ip = os.getenv('EGRESS_IP')
	if not egress_ip:
		egress_ip = get_egress_ip()

	lumen_ip = os.getenv('LUMEN_IP')

	if not egress_ip:
		raise ValueError("EGRESS_IP must be set in .env file or retrievable via get_egress_ip().")
	if not lumen_ip:
		raise ValueError("LUMEN_IP must be set in .env file.")

	# Normalize values for comparison
	egress_ip_n = egress_ip.strip()
	lumen_ip_n = lumen_ip.strip()

	if egress_ip_n == lumen_ip_n:
		bandwidth = os.getenv('BANDWIDTH_FULL')
		source = 'BANDWIDTH_FULL'
	else:
		bandwidth = os.getenv('BANDWIDTH_HEARTBEAT')
		source = 'BANDWIDTH_HEARTBEAT'

	if not bandwidth:
		raise ValueError(f"{source} must be set in .env file.")

	# Persist the chosen quote bandwidth
	_update_env_file({'QUOTE_BANDWIDTH': bandwidth})
	os.environ['QUOTE_BANDWIDTH'] = bandwidth

	print(f"Egress IP: {egress_ip_n}, LUMEN_IP: {lumen_ip_n}")
	print(f"Match: {egress_ip_n == lumen_ip_n}, QUOTE_BANDWIDTH set to: {bandwidth}")

	return bandwidth



def request_quote(product_code: str, product_name: str, bandwidth: str = None, customer_po: str = "", url: str = f"{base_url}/Product/v1/priceRequest", access_token: str = None):
    load_dotenv()

    customer_number = os.getenv('CUSTOMER_NUMBER')
    currency_code = os.getenv('CURRENCY_CODE')
    master_site_id = os.getenv('MASTER_SITE_ID')
    partner_id = os.getenv('PARTNER_ID')

    if not customer_number or not currency_code or not master_site_id or not partner_id:
        missing = [n for n, v in (
            ('CUSTOMER_NUMBER', customer_number),
            ('CURRENCY_CODE', currency_code),
					bandwidth = next(
						(pc.get('value') for pc in svc.get('productCharacteristic', []) or []
						 if pc.get('name') == 'Bandwidth'),
						None
					)
					if bandwidth:
						bw_norm = str(bandwidth).lower()
						print(f"{bw_norm}")
						env_updates['SERVICE_BANDWIDTH'] = bw_norm
						bandwidth = bw_norm
    headers = {
        'x-customer-number': customer_number,
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {access_token}'
    }

    payload = {
        "sourceSystem": "NaaS ExternalApi",
        "customerPriceRequestDescription": "NaaS Price Request",
        "customerPurchaseOrderNumber": customer_po,
        "customerNumber": customer_number,
        "currencyCode": currency_code,
        "masterSiteId": master_site_id,
        "productCode": product_code,
        "partnerId": partner_id,
        "productName": product_name,
        "speed": bandwidth
    }

    resp = requests.post(url, headers=headers, json=payload)
    try:
        resp.raise_for_status()
    except requests.HTTPError:
        print(f"Price request failed: {resp.status_code} {resp.text}")
        raise

    try:
        data = resp.json()
    except ValueError:
        print(resp.text)
        return resp.text

    quote_id = data.get('id')
    if quote_id:
        print(f"Price request id: {quote_id}")
        # attempt to append to orders helper (if available)
        try:
            from . import orders as orders_module
        except Exception:
            try:
                import orders as orders_module
            except Exception:
                orders_module = None
        if orders_module:
            try:
                orders_module.append_order(quote_id)
                print(f"Appended quote id to orders file")
            except Exception as e:
                print(f"Failed to append quote id to orders file: {e}")
    else:
        print("No id returned in price request response")

    return data


def order_request(quote_id: str, service_id: str = None, product_code: str = None, product_spec_id: str = None, product_name: str = None, quantity: int = 1, action: str = "modify", external_id: str = None, note_text: str = "This is a test", access_token: str = None, url: str = f"{base_url}/Customer/v3/Ordering/orderRequest"):
	"""
	Place an order request using env variables and a `quote_id` from a previous quote.

	Required in env (unless provided as args):
	- CUSTOMER_NUMBER
	- BILLING_ACCOUNT_ID, BILLING_ACCOUNT_NAME
	- SERVICE_ID (or pass service_id)
	- PRODUCT_CODE (or pass product_code)
	"""
	load_dotenv()

	customer_number = os.getenv('CUSTOMER_NUMBER')
	billing_id = os.getenv('BILLING_ACCOUNT_ID')
	billing_name = os.getenv('BILLING_ACCOUNT_NAME')

	service_id = service_id or os.getenv('SERVICE_ID')
	product_code = product_code or os.getenv('PRODUCT_CODE')
	product_spec_id = product_spec_id or os.getenv('PRODUCT_SPEC_ID')
	product_name = product_name or os.getenv('PRODUCT_NAME')

	if not customer_number:
		raise ValueError("CUSTOMER_NUMBER must be set in .env or passed in")
	if not billing_id or not billing_name:
		raise ValueError("BILLING_ACCOUNT_ID and BILLING_ACCOUNT_NAME must be set in .env")
	if not service_id:
		raise ValueError("service_id parameter or SERVICE_ID in .env must be provided.")
	if not product_code:
		raise ValueError("product_code parameter or PRODUCT_CODE in .env must be provided.")

	access_token = access_token or get_valid_access_token()

	headers = {
		'x-customer-number': customer_number,
		'Content-Type': 'application/json',
		'Authorization': f'Bearer {access_token}'
	}

	# build payload
	# Ensure external_id is limited to 20 characters including prefix from env
	if external_id:
		_final_external_id = str(external_id)
	else:
		prefix = os.getenv('EXTERNAL_ID_PREFIX')
		suffix = str(int(time.time()))
		# compute allowed suffix length
		max_len = 20
		allowed_suffix_len = max_len - len(prefix)
		if allowed_suffix_len <= 0:
			# prefix too long - truncate prefix to max length
			_final_external_id = prefix[:max_len]
		else:
			# use the rightmost part of suffix to keep recent uniqueness
			_final_external_id = prefix + suffix[-allowed_suffix_len:]
	# ensure final length safety
	_final_external_id = _final_external_id[:20]
	if _final_external_id != (external_id or ''):
		# update the external_id variable and notify
		external_id = _final_external_id
		print(f"Using external_id: {external_id}")
	# base payload
	payload = {
		"externalId": external_id,
		"billingAccount": {"id": billing_id, "name": billing_name},
		"channel": [{"id": 99, "name": "NaaS ExternalApi"}],
		"note": [{"text": note_text}],
		"productOrderItem": [
			{
				"id": service_id,
				"quantity": quantity,
				"action": action,
				"product": {
					"id": service_id,
					"productCharacteristic": [],
					"productSpecification": {"id": product_spec_id or "5001", "name": product_name or "NaaS Internet"}
				},
				"productOffering": {"id": product_code, "name": product_name or "Internet On-Demand"}
			}
		],
		"quote": [{"id": quote_id, "name": quote_id}],
	}

	# optional related contact info
	contact_number = os.getenv('CONTACT_NUMBER')
	contact_email = os.getenv('CONTACT_EMAIL')
	contact_role = os.getenv('CONTACT_ROLE')
	contact_org = os.getenv('CONTACT_ORG')
	contact_name = os.getenv('CONTACT_NAME')
	contact_ext = os.getenv('CONTACT_NUMBER_EXTENSION')
	if contact_number or contact_email or contact_role or contact_org or contact_name or contact_ext:
		related = {
			"number": contact_number or "",
			"emailAddress": contact_email or "",
			"role": contact_role or "",
			"organization": contact_org or "",
			"name": contact_name or "",
			"numberExtension": contact_ext or ""
		}
		payload["relatedContactInformation"] = [related]

	resp = requests.post(url, headers=headers, json=payload)
	try:
		resp.raise_for_status()
	except requests.HTTPError:
		print(f"Order request failed: {resp.status_code} {resp.text}")
		raise

	try:
		data = resp.json()
	except ValueError:
		print(resp.text)
		return resp.text

	print(f"Order response: {data}")
	return data




def main():
	"""
	Main workflow: check inventory, compare SERVICE_BANDWIDTH with QUOTE_BANDWIDTH.
	
	If SERVICE_BANDWIDTH != QUOTE_BANDWIDTH, request a price quote and end.
	If they are the same, no quote is requested.
	
	Requires .env file with:
	- USERNAME, SECRET (OAuth credentials)
	- CUSTOMER_NUMBER
	- SERVICE_ID (or passed as argument)
	- CURRENCY_CODE, PARTNER_ID (for quoting)
	- PRODUCT_CODE, PRODUCT_NAME (for quoting)
	- QUOTE_BANDWIDTH (set via set_quote_bandwidth())
	"""
	try:
		# Step 1: Check inventory
		print("=" * 50)
		print("Step 1: Checking inventory...")
		print("=" * 50)
		inventory = check_inventory()
		service_bandwidth = inventory.get('_bandwidth')
		print(f"Inventory check complete. SERVICE_BANDWIDTH: {service_bandwidth}\n")

		# Step 1.5: Set quote bandwidth based on egress IP
		print("=" * 50)
		print("Step 1.5: Setting quote bandwidth...")
		print("=" * 50)
		set_quote_bandwidth()
		print()

		# Step 2: Compare SERVICE_BANDWIDTH with QUOTE_BANDWIDTH
		load_dotenv()
		quote_bandwidth = os.getenv('QUOTE_BANDWIDTH')
		
		print("=" * 50)
		print("Step 2: Comparing bandwidth values...")
		print("=" * 50)
		print(f"SERVICE_BANDWIDTH: {service_bandwidth}")
		print(f"QUOTE_BANDWIDTH: {quote_bandwidth}")
		
		if service_bandwidth == quote_bandwidth:
			print("Bandwidths match. No quote needed.\n")
			return 0
		
		print("Bandwidths differ. Requesting price quote...\n")
		
		# Step 3: Request price quote (only if bandwidths differ)
		print("=" * 50)
		print("Step 3: Requesting price quote...")
		print("=" * 50)
		quote = request_quote(
			product_code=os.getenv('PRODUCT_CODE'),
			product_name=os.getenv('PRODUCT_NAME'),
			bandwidth=service_bandwidth
		)
		quote_id = quote.get('quoteId') or quote.get('id')
		print(f"Quote created. Quote ID: {quote_id}\n")

		print("=" * 50)
		print("Workflow complete!")
		print("=" * 50)

	except Exception as e:
		print(f"Error: {e}")
		return 1
	
	return 0


if __name__ == '__main__':
	exit(main())