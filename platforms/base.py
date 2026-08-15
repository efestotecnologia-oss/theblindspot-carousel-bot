"""Interfaccia comune a tutti gli adapter di piattaforma.

Aggiungere un nuovo social = creare una classe che eredita da
`PlatformAdapter` e implementa `publish()`. Il resto del sistema
(scheduler, coda, approvazioni) non cambia.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from core.models import Platform, Post, PublishResult


class PlatformAdapter(ABC):
    #: piattaforma gestita da questo adapter
    platform: Platform

    @abstractmethod
    def publish(self, post: Post) -> PublishResult:
        """Pubblica il post sulla piattaforma e restituisce l'esito.

        Non deve sollevare eccezioni per errori "attesi" (token scaduto,
        media non valido, ...): li incapsula in un PublishResult(ok=False).
        """
        raise NotImplementedError
