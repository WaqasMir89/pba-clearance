MAX_SOURCE_BYTES = 256 * 1024
MAX_ROWS = 500
VALIDATOR_VERSION = "complaint-csv-v1"
DECLARATION_VERSION = "sandbox-claim-v1"
DECLARATION_TEXT = (
    "I am filing these fictional reported claims for this channel in the development sandbox. "
    "The figures are reported allegations, not verified settlement or official clearance. "
    "Only the ready rows and the displayed reported total will be filed."
)
REQUIRED_HEADERS = (
    "agency_code",
    "client_code",
    "financial_year",
    "invoice_number",
    "invoice_date",
    "broadcast_start",
    "broadcast_end",
    "principal_amount",
    "gst_amount",
    "invoice_total",
    "reported_due",
    "currency",
    "delivery_reference",
)
OPTIONAL_HEADERS = (
    "invoice_delivered_on",
    "release_order_reference",
    "source_id",
    "balance_explanation",
)
HEADERS = REQUIRED_HEADERS + OPTIONAL_HEADERS
