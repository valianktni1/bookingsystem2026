"""Approved post-wedding wording and the fixed 2027 awards deadline."""
from datetime import date

from .business_time import business_today

TEMPLATE_KEY = "post_wedding_review"
REVIEW_REQUEST_KEYS = frozenset({TEMPLATE_KEY, "review_request"})
VOTING_CLOSES = date(2027, 4, 30)
GOOGLE_REVIEW_URL = "https://g.page/r/CWXyai3xrskCEBM/review"
FACEBOOK_REVIEW_URL = "https://www.facebook.com/weddingsbymarkmanchester/reviews/"
COUNTY_BRIDES_URL = "https://www.countybrides.com/awards/"

COUNTY_BRIDES_REQUEST = """I’ve got a little favour to ask. You can both vote separately, so if you each have a spare couple of minutes, I’d be really grateful!

I’m up for the County Brides North West Wedding Awards, and I’m hoping to bring the award home for the second year running! A vote for Weddings By Mark would mean a lot to me. Voting closes on 30 April 2027:

[Vote for Weddings By Mark](https://www.countybrides.com/awards/)"""

SUBJECT = "How’s married life treating you both?"
BODY = """Hey Guys,

Hope you’re both enjoying married life! Can’t believe it’s already been two weeks since your wedding. Thanks again for having me along to capture your day.

{county_brides_request}{review_request_intro} if you could leave me a review on Facebook. Hearing about your experience makes such a difference to my little business and helps other couples when they’re choosing their photographer.

[Leave a Facebook review](https://www.facebook.com/weddingsbymarkmanchester/reviews/)

If you wouldn’t mind copying and pasting your review onto Google too, I’d really appreciate it — you’re welcome to use the same words!

[Leave a Google review](https://g.page/r/CWXyai3xrskCEBM/review)

Thanks so much to you both. Hope you’re enjoying looking back through your wedding photos!

Mark
Weddings By Mark
{business_phone}"""


def voting_is_open(booking, *, today=None):
    """Use the actual UK send date, including delayed sends and retries."""
    today = today or business_today()
    return (booking.brand == "wbm" and booking.event_date is not None
            and booking.event_date <= today <= VOTING_CLOSES)


def review_template_values(booking, *, today=None):
    voting = voting_is_open(booking, today=today)
    return {
        "county_brides_request": COUNTY_BRIDES_REQUEST + "\n\n" if voting else "",
        "review_request_intro": "It would also be lovely" if voting else "It would be lovely",
    }


def enforce_review_deadline(body, booking, template_key, *, today=None):
    """Remove the approved awards section from an old rendered retry too."""
    if template_key not in REVIEW_REQUEST_KEYS or voting_is_open(booking, today=today):
        return body
    body = body.replace(COUNTY_BRIDES_REQUEST + "\n\n", "").replace(COUNTY_BRIDES_REQUEST, "")
    return body.replace("It would also be lovely if you could leave me a review",
                        "It would be lovely if you could leave me a review")


def record_review_sent(booking, *, sent_at, subject, sent_by):
    workflow = dict(booking.workflow_state or {})
    after_wedding = dict(workflow.get("after_wedding") or {})
    after_wedding["review_request"] = {
        "sent_at": sent_at.isoformat(), "sent_by": sent_by, "subject": subject,
    }
    after_wedding.update(updated_at=sent_at.isoformat(), updated_by=sent_by)
    workflow["after_wedding"] = after_wedding
    booking.workflow_state = workflow
