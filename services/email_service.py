"""
Email Service
Sends scraper results and alerts via email
"""

import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime

from config.settings import (
    SMTP_HOST,
    SMTP_PORT,
    SMTP_USER,
    SMTP_PASSWORD,
    NOTIFICATION_EMAIL,
)

logger = logging.getLogger(__name__)


class EmailService:
    """Service for sending scraper results and alerts via email"""

    def __init__(
        self,
        smtp_host: Optional[str] = None,
        smtp_port: Optional[int] = None,
        smtp_user: Optional[str] = None,
        smtp_password: Optional[str] = None,
    ):
        self.smtp_host = smtp_host or SMTP_HOST
        self.smtp_port = smtp_port or SMTP_PORT
        self.smtp_user = smtp_user or SMTP_USER
        self.smtp_password = smtp_password or SMTP_PASSWORD

        if not all([self.smtp_user, self.smtp_password]):
            logger.warning(
                "Email service initialized without credentials - emails will fail"
            )

    def send_daily_results(
        self,
        csv_files: List[Path],
        metrics: Dict,
        recipient: str,
        subject: Optional[str] = None,
    ) -> bool:
        """
        Send daily scraper results with CSV attachments

        Args:
            csv_files: List of CSV file paths to attach
            metrics: Dictionary with scraping metrics
            recipient: Email address to send to
            subject: Optional custom subject line

        Returns:
            True if email sent successfully, False otherwise
        """
        try:
            # Generate subject
            if not subject:
                date_str = datetime.now().strftime("%Y-%m-%d")
                subject = f"FanbaseHQ Scraper Results - {date_str}"

            # Generate HTML body
            html_body = self._generate_results_html(metrics, csv_files)

            # Create message
            msg = self._create_multipart_message(subject, html_body, recipient)

            # Attach CSV files
            for csv_file in csv_files:
                if not csv_file.exists():
                    logger.warning(f"CSV file not found: {csv_file}")
                    continue

                self._attach_file(msg, csv_file)

            # Send email
            return self._send_email(msg, recipient)

        except Exception as e:
            logger.error(f"Failed to send daily results email: {e}")
            return False

    def send_error_alert(
        self,
        error: Exception,
        scraper_type: str,
        recipient: str,
        additional_context: Optional[Dict] = None,
    ) -> bool:
        """
        Send error alert email

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

            # Create message
            msg = self._create_multipart_message(subject, html_body, recipient)

            # Send email
            return self._send_email(msg, recipient)

        except Exception as e:
            logger.error(f"Failed to send error alert email: {e}")
            return False

    def send_test_email(self, recipient: Optional[str] = None) -> bool:
        """
        Send test email to verify SMTP configuration

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
                <p>If you received this email, your SMTP configuration is working correctly.</p>
                <hr>
                <p style="color: #666; font-size: 12px;">
                  Sent at {timestamp}
                </p>
              </body>
            </html>
            """.format(
                timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            )

            msg = self._create_multipart_message(subject, html_body, recipient)
            return self._send_email(msg, recipient)

        except Exception as e:
            logger.error(f"Failed to send test email: {e}")
            return False

    def _create_multipart_message(
        self, subject: str, html_body: str, recipient: str
    ) -> MIMEMultipart:
        """Create a multipart MIME message"""
        msg = MIMEMultipart()
        msg["From"] = self.smtp_user
        msg["To"] = recipient
        msg["Subject"] = subject

        # Attach HTML body
        msg.attach(MIMEText(html_body, "html"))

        return msg

    def _attach_file(self, msg: MIMEMultipart, file_path: Path):
        """Attach a file to a MIME message"""
        try:
            with open(file_path, "rb") as f:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(f.read())

            encoders.encode_base64(part)
            part.add_header(
                "Content-Disposition",
                f"attachment; filename= {file_path.name}",
            )

            msg.attach(part)
            logger.debug(f"Attached file: {file_path.name}")

        except Exception as e:
            logger.error(f"Failed to attach file {file_path}: {e}")

    def _send_email(self, msg: MIMEMultipart, recipient: str) -> bool:
        """Send email via SMTP"""
        try:
            logger.info(
                f"Sending email to {recipient} via {self.smtp_host}:{self.smtp_port}"
            )

            server = smtplib.SMTP(self.smtp_host, self.smtp_port)
            server.starttls()
            server.login(self.smtp_user, self.smtp_password)
            text = msg.as_string()
            server.sendmail(self.smtp_user, recipient, text)
            server.quit()

            logger.info(f"Email sent successfully to {recipient}")
            return True

        except smtplib.SMTPAuthenticationError:
            logger.error("SMTP authentication failed - check credentials")
            return False
        except smtplib.SMTPException as e:
            logger.error(f"SMTP error: {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to send email: {e}")
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
