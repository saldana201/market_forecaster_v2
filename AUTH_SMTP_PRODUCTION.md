# Supabase Auth email delivery — production setup

Market Forecaster signup currently uses Supabase Auth email confirmation.

## Current production finding

Live Auth logs on 2026-09-25 showed signup requests failing with:

    429: email rate limit exceeded

This is an email-delivery/provider limit, not a password-validation or RLS failure.

Supabase's default email service is intended for development and is heavily restricted.
Before opening public account registration, configure a custom SMTP provider in the
Supabase project's Authentication SMTP settings.

## Recommended production checklist

1. Choose the business email provider that will send Market Forecaster transactional mail.
2. Obtain its SMTP host, port, username, password/app-password, and sender address.
3. Configure those credentials in Supabase Authentication SMTP settings.
4. Use a branded sender such as a no-reply/support address on oneeightaisystems.com.
5. Confirm the Market Forecaster custom domain is configured as an allowed Auth redirect/site URL.
6. Send test signup confirmations to at least Gmail and Outlook/Hotmail addresses.
7. Check SPF/DKIM/DMARC for the sending domain/provider.
8. Re-run account signup tests and verify Auth logs no longer show email-rate-limit failures.

Do not commit SMTP passwords or app-passwords to GitHub.

## App behavior

Market Forecaster detects Supabase email-rate-limit responses and explains that the
email provider is temporarily unavailable rather than presenting the failure as a bad
account/password request.


## Account email operations

The Account page now supports:

- resend signup confirmation for an existing unconfirmed account
- signed-in password changes through Supabase Auth

Resend responses are intentionally non-enumerating. The UI does not reveal whether the
email address exists or is already confirmed.

The resend flow is still subject to Supabase Auth email rate limits, so custom SMTP is
required for reliable production delivery.

## Password recovery boundary

A signed-in user can change their password directly.

A full "Forgot password" recovery-email flow should not be enabled until the Streamlit
application has a complete recovery-token return path. Do not ship a reset-email button
that redirects users back to a page unable to consume the recovery session securely.
