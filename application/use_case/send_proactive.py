from telegram import Bot
from datetime import datetime
from domain.service.proactive_service import ProactiveService
from infrastructure.database.repositories.user_repository import UserRepository
from infrastructure.database.repositories.user_stats_repository import UserStatsRepository
from infrastructure.database.repositories.character_repository import CharacterRepository
from presentation.telegram.message_sender import TelegramMessageSender
from infrastructure.monitoring.logging import StructuredLogger

MaxMessagesSend = 1

class SendProactiveMessageUseCase:
    def __init__(self,
                 user_repo: UserRepository,
                 user_stats_repo: UserStatsRepository,
                 character_repo: CharacterRepository,
                 proactive_service: ProactiveService,
                 telegram_sender: TelegramMessageSender):
        self.user_repo = user_repo
        self.user_stats_repo = user_stats_repo
        self.character_repo = character_repo
        self.proactive_service = proactive_service
        self.telegram_sender = telegram_sender
        self.logger = StructuredLogger('send_proactive_uc')


    async def execute(self, bot: Bot):
        self.logger.info("Starting proactive messages sending")
        users = self.user_repo.get_users_for_proactive()
        sent_count = 0
        disabled_count = 0

        for user in users:
            user_stats = self.user_stats_repo.get_user_stats(user.user_id)
            if not user_stats:
                continue

            if not user.last_proactive_sent_at:
                last_message_at = user_stats.last_message_at
            elif user_stats.last_message_at < user.last_proactive_sent_at:
                last_message_at = user.last_proactive_sent_at
            else:
                last_message_at = user_stats.last_message_at

            seconds_since_last = (datetime.utcnow() - last_message_at).total_seconds()
            if user.proactive_missed_count >= MaxMessagesSend or seconds_since_last < 86400:
                return

            if not user.current_character_id:
                continue

            message_text = await self.proactive_service.generate_proactive_message(
                user.user_id, user.current_character_id
            )

            success = await self.telegram_sender.send_message(
                bot=bot,
                chat_id=user.user_id,
                text=message_text
            )
            if success:
                now = datetime.utcnow()
                user.last_proactive_sent_at = now
                user.proactive_missed_count = user.proactive_missed_count + 1

                if user.proactive_missed_count >= MaxMessagesSend:
                    user.proactive_enabled = False

                self.user_repo.update_proactive_state(
                    user.user_id,
                    now,
                    user.proactive_missed_count,
                    user.proactive_enabled
                )
                sent_count += 1
                self.logger.info(f"Proactive message sent to user {user.user_id}")
            else:
                self.logger.error(f"Failed to send proactive to user {user.user_id}")

        self.logger.info(f"Proactive finished. Sent: {sent_count}, disabled: {disabled_count}")