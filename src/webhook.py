import asyncio
import logging
from fastapi import FastAPI, HTTPException
import uvicorn
from typing import Optional
from src.config import ENABLE_WEBHOOK

logger = logging.getLogger(__name__)

class WebhookServer:
    def __init__(self):
        self.app = FastAPI()
        self.host = "0.0.0.0"
        self.port = 8000
        self.webhook_trigger = False
        self.is_enabled = ENABLE_WEBHOOK
        self.setup_routes()

    def setup_routes(self):
        @self.app.post("/trigger")
        async def trigger_update():
            if not self.is_enabled:
                raise HTTPException(status_code=403, detail="Webhook functionality is currently disabled")
            self.webhook_trigger = True
            logger.info("Webhook triggered successfully")
            return {"message": "Update triggered successfully"}

        @self.app.get("/status")
        async def get_status():
            return {
                "webhook_enabled": self.is_enabled,
                "trigger_status": self.webhook_trigger
            }

    def get_trigger_status(self) -> bool:
        """Get current trigger status and reset it"""
        if self.webhook_trigger:
            self.webhook_trigger = False
            return True
        return False

    async def run_server(self):
        """Run the webhook server if enabled"""
        if self.is_enabled:
            logger.info(f"Starting webhook server on {self.host}:{self.port}")
            config = uvicorn.Config(
                self.app,
                host=self.host,
                port=self.port,
                log_level="info"
            )
            server = uvicorn.Server(config)
            await server.serve()
        else:
            logger.info("Webhook server disabled")
            # If webhooks are disabled, just wait indefinitely
            while True:
                await asyncio.sleep(3600)  # Sleep for an hour