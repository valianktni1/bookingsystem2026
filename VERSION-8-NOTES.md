# Version 8 - client experience and venue search

This is a cumulative update. It contains every file and feature from V7A.

## New in V8

- Branded Weddings By Mark and Ivory Digital client themes
- Real business logos in the portal and admin sign-in
- Wedding countdown and clearer welcome area
- Journey progress, completion ticks and next-step guidance
- Three-step responsive Wedding Booking Form
- Improved mobile navigation, invoices and empty states
- Google Places venue autocomplete on the public enquiry form
- Google Places venue autocomplete in the admin record editor
- Venue address, Place ID and coordinates stored safely against the booking
- Underlined one-click Google Maps directions in the admin booking overview
- Admin attention cards and enquiry badge
- Branded email preview and explicit send-test controls

## Google key

Add the restricted key to the app environment:

```yaml
GOOGLE_MAPS_API_KEY: YOUR_RESTRICTED_KEY
```

Do not commit the real key to GitHub. Put it only in the private Dockge compose environment.

## Safe deployment

Upload the complete contents of the V8 ZIP to the root of the GitHub repository, then run:

```bash
docker compose -f /mnt/apps/dockge/data/bookingsystem2026/compose.yaml down
docker compose -f /mnt/apps/dockge/data/bookingsystem2026/compose.yaml build --no-cache app
docker compose -f /mnt/apps/dockge/data/bookingsystem2026/compose.yaml up -d
```

The startup migration only adds nullable venue columns. Existing bookings, invoices, payments,
contracts, forms, templates, documents and email history are preserved.
