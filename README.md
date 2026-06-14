# CloudDB Maintenance Fee Collection - Algorand Integration

This project adds optional Algorand payment support to the CloudDB maintenance fee system.

Quick setup

1. Install Python dependencies:

```bash
pip install -r requirements.txt
```

2. Environment variables (example using PureStake/testnet):

```powershell
$env:ALGOD_ADDRESS="https://testnet-algorand.api.purestake.io/ps2"
$env:ALGOD_TOKEN="<your-purestake-token>"
$env:INDEXER_ADDRESS="https://testnet-algorand.api.purestake.io/idx2"
$env:INDEXER_TOKEN="<your-token>"
$env:ALGORAND_RECEIVER_ADDRESS="<your-receiver-address>"
$env:ALGORAND_SERVER_MNEMONIC="<server-account-mnemonic>"  # only if you want server sends
$env:START_ALGORAND_WORKER=true
$env:USE_ALGORAND_INDEXER=true
$env:ALGORAND_CONFIG_STRICT=true  # optional: app startup fails if receiver address is invalid/missing
```

3. Run the app:

```bash
python app.py
```

Workflow notes

- When a user clicks "Pay Now" the app creates a payment invoice and returns an `invoice_id` (displayed in flash). Users should include the invoice id as the Algorand transaction note when sending ALGO from their wallet.
- If users paste a tx id into the pay form, the system will attempt to verify it immediately.
- A background worker scans pending payments and the configured receiver address (via Algorand Indexer) to auto-confirm transactions that include the invoice id in the tx note.
 - The user invoice page includes a QR code (Algorand URI) to simplify payment from mobile wallets.
 - Administrators can validate Algorand receiver setup in the UI at `/admin/chain/config`.
 - A webhook endpoint is available at `/webhook/algorand` for real-time confirmations. Configure your Indexer or provider to POST {"txid":"...","invoice_id":"..."}.
 - Optional email receipts are sent when payments are confirmed. Configure SMTP settings via env vars (`SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `EMAIL_FROM`).
 - File uploads (user and dbmanager) now include:
	 - encryption at upload,
	 - cloud backup (local cloud folder by default, S3 optional),
	 - blockchain hash anchoring (stores file SHA-256 in Algorand tx note when configured).

Database storage location

- Default database file: `data/database.json`
- Can be changed with env var `DATA_DIR` (database path becomes `<DATA_DIR>/database.json`).

Cloud storage setup

- Default mode (no cloud account needed):
	- `CLOUD_PROVIDER=local`
	- files are copied to `data/cloud_storage/`
- S3/S3-compatible mode:
	- `CLOUD_PROVIDER=s3`
	- `S3_BUCKET=<bucket>`
	- `S3_REGION=<region>`
	- `S3_ACCESS_KEY_ID=<key>`
	- `S3_SECRET_ACCESS_KEY=<secret>`
	- optional: `S3_ENDPOINT_URL=<endpoint>` (for MinIO/other S3-compatible services)

Admin diagnostics

- Storage/runtime diagnostics page: `/admin/system/storage`
- Shows:
	- exact absolute database path at runtime,
	- upload and cloud roots,
	- cloud/blockchain failed file counts,
	- whether retry worker is enabled.

Blockchain file anchoring

- Uses existing Algorand config and server mnemonic:
	- `ALGORAND_RECEIVER_ADDRESS`
	- `ALGORAND_SERVER_MNEMONIC`
	- `ALGOD_ADDRESS`
	- `ALGOD_TOKEN`
- On each file upload, app computes SHA-256 and submits a note transaction:
	- `FILE_HASH:<sha256>:<filename>`
- Optional anchor amount override:
	- `ALGORAND_FILE_ANCHOR_AMOUNT=0.001`

Automatic retries for failed cloud/blockchain sync

- Enable worker:
	- `START_FILE_RETRY_WORKER=true`
- Configure interval in seconds:
	- `FILE_RETRY_INTERVAL=180`
- Worker behavior:
	- retries cloud upload when `cloud_status` is empty or starts with `Error:`
	- retries blockchain anchoring when `blockchain_status` is empty, `Failed`, or starts with `Error:`
- Manual trigger in admin UI:
	- POST `/admin/system/storage/retry-now` (button available on `/admin/system/storage`)

Security

- Never commit `ALGORAND_SERVER_MNEMONIC` to source control. Use a secrets manager in production.
- Use HTTPS and secure session secrets.

Files of interest

- `algorand.py` — helper to verify txids.
- `algorand_indexer.py` — optional Indexer helper to query transactions by address.
- `algorand_server.py` — server wallet helper (send payments).
- `algorand_worker.py` — background worker to verify/poll transactions.
- `routes/admin.py` + `templates/admin/algorand.html` — admin UI for chain view and exports.
- `routes/user.py` + `templates/user/fees.html` — payment flow and invoice display.

Testing

- To run the worker manually:

```bash
python algorand_worker.py
```

- To export CSV of Algorand payments use `/admin/chain/export` in the admin UI.

If you want, I can add invoice QR codes, automated email receipts, or integrate a webhook provider for real-time confirmations.
