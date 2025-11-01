from typing import Dict, Any
from dataclasses import dataclass
from infrastructure.monitoring.logging import StructuredLogger
from infrastructure.database.database import Database
from infrastructure.ai.ai_factory import AIFactory


@dataclass
class HealthStatus:
    status: str
    details: Dict[str, Any]
    timestamp: str


class HealthChecker:
    def __init__(self, database: Database):
        self.logger = StructuredLogger("health")
        self.database = database
        self.ai_client = AIFactory.create_client()
        self.checks = {
            'database': self.check_database,
            'ai_provider': self.check_ai_provider,
            'memory': self.check_memory
        }

    def check_database(self) -> Dict[str, Any]:
        try:
            self.database.execute_query("SELECT 1")
            return {"status": "healthy", "response_time_ms": 0}
        except Exception as e:
            self.logger.error(f"Database health check failed: {e}")
            return {"status": "unhealthy", "error": str(e)}

    def check_ai_provider(self) -> Dict[str, Any]:
        """Проверить доступность AI провайдера"""
        provider = os.getenv("AI_PROVIDER", "ollama")
        try:
            # Простая проверка для каждого провайдера
            if provider == "ollama":
                import requests
                response = requests.get(f"{os.getenv('OLLAMA_URL', 'http://localhost:11434')}/api/tags", timeout=10)
                status = "healthy" if response.status_code == 200 else "unhealthy"
                return {"status": status, "provider": "ollama"}

            elif provider == "openai":
                # Проверка через простой запрос
                test_messages = [{"role": "user", "content": "Hello"}]
                response = self.ai_client.generate_response(test_messages, max_tokens=10)
                return {"status": "healthy", "provider": "openai", "test_response_length": len(response)}

            elif provider == "gemini":
                # Gemini проверка
                test_messages = [{"role": "user", "content": "Hello"}]
                response = self.ai_client.generate_response(test_messages, max_tokens=10)
                return {"status": "healthy", "provider": "gemini", "test_response_length": len(response)}

            elif provider == "huggingface":
                # HF проверка
                test_messages = [{"role": "user", "content": "Hello"}]
                response = self.ai_client.generate_response(test_messages, max_tokens=10)
                return {"status": "healthy", "provider": "huggingface", "test_response_length": len(response)}

            else:
                return {"status": "unknown", "provider": provider, "error": "Unknown provider"}

        except Exception as e:
            self.logger.error(f"AI provider health check failed: {e}")
            return {"status": "unhealthy", "provider": provider, "error": str(e)}

    def check_memory(self) -> Dict[str, Any]:
        import psutil
        process = psutil.Process()
        memory_info = process.memory_info()

        return {
            "status": "healthy",
            "memory_usage_mb": round(memory_info.rss / 1024 / 1024, 2),
            "memory_percent": round(process.memory_percent(), 2)
        }

    def perform_health_check(self) -> HealthStatus:
        results = {}
        overall_status = "healthy"

        for check_name, check_func in self.checks.items():
            try:
                result = check_func()
                results[check_name] = result

                if result["status"] == "unhealthy":
                    overall_status = "unhealthy"
                elif result["status"] == "degraded" and overall_status == "healthy":
                    overall_status = "degraded"

            except Exception as e:
                self.logger.error(f"Health check {check_name} failed: {e}")
                results[check_name] = {"status": "unhealthy", "error": str(e)}
                overall_status = "unhealthy"

        return HealthStatus(
            status=overall_status,
            details=results,
            timestamp=__import__('datetime').datetime.utcnow().isoformat() + "Z"
        )