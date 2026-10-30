from rest_framework.exceptions import APIException


class CommandConflict(APIException):
    status_code = 409
    default_code = "idempotency_conflict"
    default_detail = "This request reference was already used with different content."


class PreviewChanged(CommandConflict):
    default_code = "stale_preview"
    default_detail = "The import review has changed. Refresh and review it before filing."


class AlreadyFiled(CommandConflict):
    default_code = "already_filed"
    default_detail = "This import has already been filed. Open its existing receipt."


class FilingWindowClosed(CommandConflict):
    default_code = "filing_window_closed"
    default_detail = "The simulation time is outside this candidate calendar's filing window."
