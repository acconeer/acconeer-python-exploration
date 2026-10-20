# Copyright (c) Acconeer AB, 2024-2026
# All rights reserved

import json


# Errors that can occur in common "from_json" functions;
# - JSONDecodeError from trying to parse invalid JSON
# - TypeError from the parsed dict not matching the kwargs
#   of the __init__ when destructured.
FROM_JSON = (json.JSONDecodeError, TypeError)
