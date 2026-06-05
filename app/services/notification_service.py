import firebase_admin
from firebase_admin import credentials, messaging
import logging

logger = logging.getLogger(__name__)

# Initializes the Firebase Admin SDK
# Make sure the path to your firebase-service-account.json is correct!
try:
    if not firebase_admin._apps:
        cred = credentials.Certificate("firebase-service-account.json")
        firebase_admin.initialize_app(cred)
        logger.info("Firebase Admin SDK initialized successfully.")
except Exception as e:
    logger.error(f"Failed to initialize Firebase: {e}")

async def send_push_notification(fcm_token: str, title: str, body: str, data: dict = None) -> bool:
    """
    Dispatches a push notification to a specific device.
    """
    try:
        # Construct the message payload
        message = messaging.Message(
            notification=messaging.Notification(
                title=title,
                body=body,
            ),
            data=data if data else {},
            token=fcm_token,
        )

        # Send the message
        response = messaging.send(message)
        logger.info(f"Successfully sent message: {response}")
        return True
        
    except Exception as error:
        logger.error(f"Error sending push notification: {error}")
        return False