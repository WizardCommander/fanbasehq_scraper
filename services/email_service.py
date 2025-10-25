"""
Email Service
Sends scraper results and alerts via email using SendGrid HTTP API
"""

import logging
import base64
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime

from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import (
    Mail,
    Email,
    To,
    Content,
    Attachment,
    FileContent,
    FileName,
    FileType,
    Disposition,
)

from config.settings import (
    SENDGRID_API_KEY,
    SENDGRID_FROM_EMAIL,
    NOTIFICATION_EMAIL,
)

logger = logging.getLogger(__name__)


class EmailService:
    """Service for sending scraper results and alerts via email using SendGrid HTTP API"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        from_email: Optional[str] = None,
    ):
        self.api_key = api_key or SENDGRID_API_KEY
        self.from_email = from_email or SENDGRID_FROM_EMAIL

        if not self.api_key:
            logger.warning(
                "Email service initialized without SendGrid API key - emails will fail"
            )

        if not self.from_email:
            logger.warning(
                "Email service initialized without from_email - emails will fail"
            )

    def send_daily_results(
        self,
        csv_files: List[Path],
        metrics: Dict,
        recipient: str,
        subject: Optional[str] = None,
    ) -> bool:
        """
        Send daily scraper results with CSV attachments via SendGrid HTTP API

        Args:
            csv_files: List of CSV file paths to attach
            metrics: Dictionary with scraping metrics
            recipient: Email address to send to
            subject: Optional custom subject line

        Returns:
            True if email sent successfully, False otherwise
        """
        try:
            logger.info("=== Starting send_daily_results ===")

            # Generate subject
            if not subject:
                date_str = datetime.now().strftime("%Y-%m-%d")
                subject = f"FanbaseHQ Scraper Results - {date_str}"
            logger.info(f"Subject generated: {subject}")

            # Generate HTML body
            logger.info("Generating HTML body...")
            html_body = self._generate_results_html(metrics, csv_files)
            logger.info(f"HTML body generated: {len(html_body)} bytes")

            # Create SendGrid message
            logger.info("Creating SendGrid Mail object...")
            message = Mail(
                from_email=Email(self.from_email),
                to_emails=To(recipient),
                subject=subject,
                html_content=Content("text/html", html_body),
            )

            # Attach CSV files
            logger.info(f"Attaching {len(csv_files)} CSV files...")
            for i, csv_file in enumerate(csv_files, 1):
                if not csv_file.exists():
                    logger.warning(f"CSV file not found: {csv_file}")
                    continue

                logger.info(f"Attaching file {i}/{len(csv_files)}: {csv_file.name}")
                self._attach_file_to_sendgrid(message, csv_file)
                logger.info(f"File {i}/{len(csv_files)} attached successfully")

            logger.info("All attachments complete, preparing to send...")

            # Send email via SendGrid API
            result = self._send_via_sendgrid(message, recipient)
            logger.info(f"Send result: {result}")
            return result

        except Exception as e:
            logger.error(f"Failed to send daily results email: {e}", exc_info=True)
            return False

    def send_error_alert(
        self,
        error: Exception,
        scraper_type: str,
        recipient: str,
        additional_context: Optional[Dict] = None,
    ) -> bool:
        """
        Send error alert email via SendGrid HTTP API

        Args:
            error: Exception that occurred
            scraper_type: Type of scraper that failed (milestone, tunnel_fit, shoe)
            recipient: Email address to send to
            additional_context: Optional additional context info

        Returns:
            True if email sent successfully, False otherwise
        """
        try:
            # Generate subject
            subject = f"⚠️ FanbaseHQ Scraper Error - {scraper_type}"

            # Generate HTML body
            html_body = self._generate_error_html(
                error, scraper_type, additional_context
            )

            # Create SendGrid message
            message = Mail(
                from_email=Email(self.from_email),
                to_emails=To(recipient),
                subject=subject,
                html_content=Content("text/html", html_body),
            )

            # Send email via SendGrid API
            return self._send_via_sendgrid(message, recipient)

        except Exception as e:
            logger.error(f"Failed to send error alert email: {e}")
            return False

    def send_test_email(self, recipient: Optional[str] = None) -> bool:
        """
        Send test email to verify SendGrid API configuration

        Args:
            recipient: Email address to send to (defaults to NOTIFICATION_EMAIL)

        Returns:
            True if email sent successfully, False otherwise
        """
        try:
            recipient = recipient or NOTIFICATION_EMAIL
            if not recipient:
                logger.error("No recipient specified for test email")
                return False

            subject = "FanbaseHQ Scraper - Test Email"
            html_body = """
            <html>
              <body>
                <h2>✅ Email Configuration Test</h2>
                <p>This is a test email from the FanbaseHQ scraper.</p>
                <p>If you received this email, your SendGrid API configuration is working correctly.</p>
                <hr>
                <p style="color: #666; font-size: 12px;">
                  Sent at {timestamp}
                </p>
              </body>
            </html>
            """.format(
                timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            )

            # Create SendGrid message
            message = Mail(
                from_email=Email(self.from_email),
                to_emails=To(recipient),
                subject=subject,
                html_content=Content("text/html", html_body),
            )

            return self._send_via_sendgrid(message, recipient)

        except Exception as e:
            logger.error(f"Failed to send test email: {e}")
            return False

    def _attach_file_to_sendgrid(self, message: Mail, file_path: Path):
        """Attach a file to a SendGrid Mail object"""
        try:
            logger.debug(f"Reading file: {file_path}")
            with open(file_path, "rb") as f:
                file_data = f.read()
            logger.debug(f"File read complete: {len(file_data)} bytes")

            logger.debug("Encoding to base64...")
            encoded_file = base64.b64encode(file_data).decode()
            logger.debug("Base64 encoding complete")

            logger.debug("Creating SendGrid Attachment...")
            attachment = Attachment(
                FileContent(encoded_file),
                FileName(file_path.name),
                FileType("text/csv"),
                Disposition("attachment"),
            )
            logger.debug("Attachment created")

            logger.debug("Adding attachment to message...")
            message.add_attachment(attachment)
            logger.debug(f"Attached file: {file_path.name}")

        except Exception as e:
            logger.error(f"Failed to attach file {file_path}: {e}", exc_info=True)

    def _send_via_sendgrid(self, message: Mail, recipient: str) -> bool:
        """Send email via SendGrid HTTP API"""
        try:
            logger.info(f"Sending email to {recipient} via SendGrid API")

            if not self.api_key:
                logger.error("SendGrid API key not configured")
                return False

            logger.info("Creating SendGrid API client...")
            sg = SendGridAPIClient(self.api_key)

            logger.info("Sending email via HTTPS...")
            response = sg.send(message)

            logger.info(f"SendGrid response status: {response.status_code}")
            logger.debug(f"SendGrid response body: {response.body}")
            logger.debug(f"SendGrid response headers: {response.headers}")

            if response.status_code in [200, 201, 202]:
                logger.info(f"Email sent successfully to {recipient}")
                return True
            else:
                logger.error(
                    f"SendGrid returned unexpected status: {response.status_code}"
                )
                return False

        except Exception as e:
            logger.error(f"Failed to send email via SendGrid: {e}", exc_info=True)
            return False

    def _generate_results_html(self, metrics: Dict, csv_files: List[Path]) -> str:
        """Generate HTML body for results email"""
        date_str = datetime.now().strftime("%Y-%m-%d")

        # Build CSV file list
        csv_list_html = ""
        for csv_file in csv_files:
            if csv_file.exists():
                size_kb = csv_file.stat().st_size / 1024
                csv_list_html += f"<li>{csv_file.name} ({size_kb:.1f} KB)</li>"

        # Build metrics HTML
        metrics_html = ""
        for key, value in metrics.items():
            metrics_html += f"<tr><td style='padding: 8px; border-bottom: 1px solid #ddd;'>{key}</td><td style='padding: 8px; border-bottom: 1px solid #ddd;'><strong>{value}</strong></td></tr>"

        html = f"""
        <html>
          <head>
            <style>
              body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
              .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
              .header {{ background-color: #4CAF50; color: white; padding: 20px; text-align: center; }}
              .content {{ padding: 20px; background-color: #f9f9f9; }}
              .metrics {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
              .footer {{ margin-top: 20px; padding: 10px; text-align: center; color: #666; font-size: 12px; }}
            </style>
          </head>
          <body>
            <div class="container">
              <div class="header">
                <h1>📊 FanbaseHQ Scraper Results</h1>
                <p>{date_str}</p>
              </div>
              <div class="content">
                <h2>Summary</h2>
                <table class="metrics">
                  {metrics_html}
                </table>

                <h2>Attached Files</h2>
                <ul>
                  {csv_list_html}
                </ul>

                <p style="margin-top: 20px;">
                  <strong>Next Steps:</strong> Download and import the CSV files into your Supabase database.
                </p>
              </div>
              <div class="footer">
                <p>Automated email from FanbaseHQ Scraper</p>
                <p>Generated at {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
              </div>
            </div>
          </body>
        </html>
        """

        return html

    def _generate_error_html(
        self,
        error: Exception,
        scraper_type: str,
        additional_context: Optional[Dict] = None,
    ) -> str:
        """Generate HTML body for error alert email"""
        context_html = ""
        if additional_context:
            for key, value in additional_context.items():
                context_html += f"<tr><td style='padding: 8px; border-bottom: 1px solid #ddd;'>{key}</td><td style='padding: 8px; border-bottom: 1px solid #ddd;'>{value}</td></tr>"

        html = f"""
        <html>
          <head>
            <style>
              body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
              .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
              .header {{ background-color: #f44336; color: white; padding: 20px; text-align: center; }}
              .content {{ padding: 20px; background-color: #f9f9f9; }}
              .error-box {{ background-color: #ffebee; border-left: 4px solid #f44336; padding: 15px; margin: 20px 0; }}
              .context {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
              .footer {{ margin-top: 20px; padding: 10px; text-align: center; color: #666; font-size: 12px; }}
            </style>
          </head>
          <body>
            <div class="container">
              <div class="header">
                <h1>⚠️ Scraper Error Alert</h1>
                <p>{scraper_type} scraper failed</p>
              </div>
              <div class="content">
                <h2>Error Details</h2>
                <div class="error-box">
                  <p><strong>Error Type:</strong> {type(error).__name__}</p>
                  <p><strong>Message:</strong> {str(error)}</p>
                </div>

                {"<h2>Context</h2><table class='context'>" + context_html + "</table>" if context_html else ""}

                <p style="margin-top: 20px;">
                  <strong>Action Required:</strong> Please check the scraper logs for more details and resolve the issue.
                </p>
              </div>
              <div class="footer">
                <p>Automated alert from FanbaseHQ Scraper</p>
                <p>Generated at {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
              </div>
            </div>
          </body>
        </html>
        """

        return html
