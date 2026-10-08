# Property Owner Update (newsletter)

## Unreleased
- Brand: optional `brand.font_link` loads the member's web fonts where the client honours them; the header logo tile keeps a wide logo's shape.
- Setup: brand is asked as three things (logo, colours, fonts); with no brand kit, read them off the member's website and confirm. Config carries `company.mcp_connector_url`.
- Shares the loader fix for vacancy age on single-unit properties (unknown ages are never 0).
- Docs: the connector URL is per organization and Claude Team admins add custom connectors; `survey.json` is never overwritten by an empty or wrong-company pull; owner directory exports should include inactive owners.
