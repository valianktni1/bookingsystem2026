"""Personal WBM email defaults; only exact former defaults are upgraded."""

PERSONAL_EMAIL_DEFAULTS = {'quote': ('Your wedding photography quote',
           'Hi {client_first_name},\n'
           '\n'
           'Thanks for getting in touch about your wedding on {event_date} at {venue_or_project}. '
           "I'm available on your date and would love to photograph your day.\n"
           '\n'
           "I've put your quote together below. You can compare the packages, add any extras and "
           'see the total before deciding.\n'
           '\n'
           '[View your quote]({portal_url})\n'
           '\n'
           "If you'd like to go ahead, choose your package and accept the quote. Your itemised "
           'invoice will then be ready in your wedding account. The booking fee is due within one '
           'day of accepting, and your date is secured as soon as I receive your first payment.\n'
           '\n'
           'Your invoice includes the bank details. Please use **{payment_reference}** as your '
           'reference when paying.\n'
           '\n'
           "If you're unsure about anything, just reply or give me a ring on {business_phone}.\n"
           '\n'
           'Thanks,\n'
           'Mark'),
 'quote_followup_1': ('Did your wedding quote come through?',
                      'Hi {client_first_name},\n'
                      '\n'
                      "Just checking the quote I sent yesterday came through. If you can't see it, "
                      'it might be in your junk folder.\n'
                      '\n'
                      '[View your quote]({portal_url})\n'
                      '\n'
                      "If you've got any questions about the packages, just reply and I'll help.\n"
                      '\n'
                      'Thanks,\n'
                      'Mark'),
 'quote_followup_final': ('Any thoughts on your wedding quote?',
                          'Hi {client_first_name},\n'
                          '\n'
                          'Have you both had a chance to look through your wedding quote?\n'
                          '\n'
                          '[View your quote]({portal_url})\n'
                          '\n'
                          "If you're still deciding or want to talk through the options, give me a "
                          "shout. If you've made other plans, that's fine too â€” just let me "
                          'know.\n'
                          '\n'
                          'Thanks,\n'
                          'Mark')}

FORMER_EMAIL_DEFAULTS = {'quote': ('Your Weddings By Mark wedding quote',
           'Hi {client_first_name},\n'
           '\n'
           'Thank you for considering Weddings By Mark to capture your special day. I am thrilled '
           'to let you know that I still have your wedding date, {event_date}, available, and I '
           'would be honoured to be a part of it.\n'
           '\n'
           'I understand that planning a wedding can feel overwhelming, but I am here to make the '
           'photography part as easy and stress-free as possible.\n'
           '\n'
           'That is why I have put together a tailored quote specifically for your wedding at '
           '{venue_or_project}, with all of my available packages and optional extras. You can '
           'compare everything, make your choices and accept the quote through my online booking '
           'system.\n'
           '\n'
           '[VIEW YOUR FULL QUOTE HERE]({portal_url})\n'
           '\n'
           'If you are happy to go ahead, your chosen package and any extras will be saved and '
           'your itemised invoice will be created automatically. The booking fee shown for your '
           'chosen package is due within one day of accepting the quote, and your wedding date is '
           'secured as soon as I receive your first payment.\n'
           '\n'
           'Why choose Weddings By Mark? Because I believe your wedding day is just as important '
           'to me as it is to you. I am committed to creating timeless images that will become '
           'cherished memories for years to come. With my experience, creativity and attention to '
           'detail, you can relax knowing that every precious moment will be captured '
           'beautifully.\n'
           '\n'
           'I am more than happy to answer any questions or provide any additional information. '
           'Simply reply to this email or give me a call on {business_phone}, and I will be '
           'delighted to help.\n'
           '\n'
           'Bank-transfer details\n'
           'Account name: {bank_account_name}\n'
           'Sort code: {bank_sort_code}\n'
           'Account number: {bank_account_number}\n'
           '\n'
           'Once you have accepted your quote, please use **{payment_reference}** as your '
           'bank-transfer payment reference.\n'
           '\n'
           'Lastly, I would like to wish you both all the very best for your upcoming wedding day '
           'and your future together. I look forward to hearing from you and hopefully being a '
           'part of your special day.\n'
           '\n'
           'Warmest wishes,\n'
           'Mark\n'
           'Weddings By Mark'),
 'quote_followup_1': ('Just checking you received your wedding quote',
                      'Hi {client_first_name},\n'
                      '\n'
                      'I just wanted to check that the wedding quote I sent yesterday reached you '
                      'safely. Emails occasionally find their way into spam or junk folders, so '
                      'when you have a moment would you mind checking there if you cannot see it?\n'
                      '\n'
                      'Here is your wedding booking link again:\n'
                      '{portal_url}\n'
                      '\n'
                      'There is absolutely no pressure. If you have any questions or would like to '
                      'talk through the packages, just reply to this email and I will be happy to '
                      'help.\n'
                      '\n'
                      'Thanks,\n'
                      'Mark\n'
                      'Weddings By Mark'),
 'quote_followup_final': ('A final quick check about your wedding quote',
                          'Hi {client_first_name},\n'
                          '\n'
                          'I just wanted to make one final quick check that you received your '
                          'Weddings By Mark quote and were able to open it.\n'
                          '\n'
                          'You can view it here whenever you are ready:\n'
                          '{portal_url}\n'
                          '\n'
                          'If your plans have changed, that is completely fine. If you would like '
                          'any help choosing a package or have a question, simply reply and I will '
                          'be happy to help.\n'
                          '\n'
                          'Thanks,\n'
                          'Mark\n'
                          'Weddings By Mark')}

def upgrade_personal_email_defaults(template):
    """Preserve any subject/body that Mark has edited, and inactive flags."""
    key = template.template_key
    if key not in PERSONAL_EMAIL_DEFAULTS:
        return False
    if (template.subject, template.body) != FORMER_EMAIL_DEFAULTS[key]:
        return False
    template.subject, template.body = PERSONAL_EMAIL_DEFAULTS[key]
    return True
