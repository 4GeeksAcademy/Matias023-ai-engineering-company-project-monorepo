"""Controlador de generación WebSocket por sesión TrackFlow."""

import asyncio

from chat_realtime import envelope


class ChatGenerationManager:
    """Gestiona productores asíncronos dentro de un proceso."""

    def __init__(self, store, bus):
        self.store = store
        self.bus = bus
        self._tasks = {}
        self._lock = asyncio.Lock()

    async def start(
        self,
        *,
        session_id,
        user_id,
        client_id,
        text,
        producer,
    ):
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Mensaje vacío")

        if len(text) > 1000:
            raise ValueError("Mensaje demasiado largo")

        async with self._lock:
            session = self.store.get(
                session_id,
                user_id=user_id,
                client_id=client_id,
            )

            if session.status == "closed":
                raise ValueError("Sesión cerrada")

            task = self._tasks.get(session_id)

            if task is not None and not task.done():
                raise ValueError("Generación activa")

            self.store.add_message(
                session_id,
                user_id=user_id,
                client_id=client_id,
                role="user",
                content=text,
            )

            self.store.set_status(
                session_id,
                user_id=user_id,
                client_id=client_id,
                status="active",
            )

            message_id = self.store.add_message(
                session_id,
                user_id=user_id,
                client_id=client_id,
                role="assistant",
            )

            task = asyncio.create_task(
                self._run(
                    session_id=session_id,
                    user_id=user_id,
                    client_id=client_id,
                    message_id=message_id,
                    producer=producer,
                )
            )

            self._tasks[session_id] = task

            # Consumir excepciones no observadas si el WebSocket
            # ya se desconectó. Los await externos siguen funcionando.
            task.add_done_callback(
                lambda completed: (
                    None
                    if completed.cancelled()
                    else completed.exception()
                )
            )

            return message_id

    async def _run(
        self,
        *,
        session_id,
        user_id,
        client_id,
        message_id,
        producer,
    ):
        try:
            final_result = None
            structured = False

            async for item in producer:
                if isinstance(item, dict):
                    structured = True
                    kind = item.get("kind")

                    if kind == "final":
                        result = item.get("result")

                        if (
                            final_result is not None
                            or not isinstance(result, dict)
                            or not isinstance(
                                result.get("answer"), str
                            )
                            or not isinstance(
                                result.get("abstained"), bool
                            )
                        ):
                            raise ValueError(
                                "Resultado final inválido"
                            )

                        final_result = result
                        continue

                    if kind != "token" or final_result is not None:
                        raise ValueError(
                            "Evento interno inválido"
                        )

                    token = item.get("text")
                else:
                    if structured:
                        raise ValueError(
                            "Productor mixto no permitido"
                        )
                    token = item

                if not isinstance(token, str) or not token:
                    continue

                sequence = self.store.append_token(
                    message_id,
                    session_id=session_id,
                    user_id=user_id,
                    client_id=client_id,
                    token=token,
                )

                await self.bus.publish(
                    session_id,
                    envelope(
                        "token_chunk",
                        {
                            "session_id": session_id,
                            "token": token,
                            "sequence": sequence,
                        },
                    ),
                )

            if structured and final_result is None:
                raise RuntimeError(
                    "Generación terminada sin validación final"
                )

            if final_result is not None:
                self.store.replace_message_content(
                    message_id,
                    session_id=session_id,
                    user_id=user_id,
                    client_id=client_id,
                    content=final_result["answer"],
                )

            self.store.finish_message(
                message_id,
                session_id=session_id,
                user_id=user_id,
                client_id=client_id,
                status="completed",
            )

            if final_result is not None:
                await self.bus.publish(
                    session_id,
                    self.store.snapshot(
                        session_id,
                        user_id=user_id,
                        client_id=client_id,
                    ),
                )

            await self.bus.publish(
                session_id,
                envelope(
                    "generation_completed",
                    {
                        "session_id": session_id,
                        "message_id": message_id,
                    },
                ),
            )

        except asyncio.CancelledError:
            self.store.finish_message(
                message_id,
                session_id=session_id,
                user_id=user_id,
                client_id=client_id,
                status="interrupted",
            )

            self.store.set_status(
                session_id,
                user_id=user_id,
                client_id=client_id,
                status="interrupted",
            )

            raise

        except Exception as exc:
            # Registrar solo el tipo de error: nunca credenciales,
            # mensajes del usuario ni detalles potencialmente sensibles.
            import logging
            logging.getLogger(__name__).error(
                "TrackFlow chat generation failed: %s",
                type(exc).__name__,
            )

            # No emitir generation_completed ante fallos.

            # No conservar como válida una respuesta provisional fallida.
            self.store.replace_message_content(
                message_id,
                session_id=session_id,
                user_id=user_id,
                client_id=client_id,
                content="No fue posible completar la respuesta. Inténtalo nuevamente.",
            )

            self.store.finish_message(
                message_id,
                session_id=session_id,
                user_id=user_id,
                client_id=client_id,
                status="interrupted",
            )

            self.store.set_status(
                session_id,
                user_id=user_id,
                client_id=client_id,
                status="interrupted",
            )


            # Recuperar el historial corregido antes de notificar.
            await self.bus.publish(
                session_id,
                self.store.snapshot(
                    session_id,
                    user_id=user_id,
                    client_id=client_id,
                ),
            )

            await self.bus.publish(
                session_id,
                envelope(
                    "generation_interrupted",
                    {
                        "session_id": session_id,
                        "message_id": message_id,
                        "status": "interrupted",
                    },
                ),
            )

            raise

    async def interrupt(
        self,
        *,
        session_id,
        user_id,
        client_id,
    ):
        async with self._lock:
            self.store.get(
                session_id,
                user_id=user_id,
                client_id=client_id,
            )

            task = self._tasks.get(session_id)

            if task is None or task.done():
                return False

            task.cancel()

            try:
                await task
            except asyncio.CancelledError:
                pass

            # No confirmar interrupción si la tarea falló
            # por otro motivo o ignoró la cancelación.
            if not task.cancelled():
                return False

            snapshot = self.store.snapshot(
                session_id,
                user_id=user_id,
                client_id=client_id,
            )

            messages = snapshot["data"]["messages"]

            interrupted = [
                item for item in messages
                if item["role"] == "assistant"
                and item["status"] == "interrupted"
            ]

            if not interrupted:
                return False

            message_id = interrupted[-1]["message_id"]

            await self.bus.publish(
                session_id,
                envelope(
                    "generation_interrupted",
                    {
                        "session_id": session_id,
                        "message_id": message_id,
                        "status": "interrupted",
                    },
                ),
            )

            return True
