"""
DGA Scoring Service — gRPC Server
Implements ScoringServiceServicer using EnsembleScorer
"""
from __future__ import annotations

import time
from concurrent import futures

import grpc

from common.config import get_settings
from common.observability import get_logger, SCORE_REQUESTS, SCORE_LATENCY, DGA_HITS
from ai.scoring.proto import scoring_pb2, scoring_pb2_grpc

logger = get_logger(__name__)


class ScoringServiceImpl(scoring_pb2_grpc.ScoringServiceServicer):
    """gRPC implementation of the scoring service."""

    def __init__(self, scorer):
        self.scorer = scorer

    def ScoreDomain(self, request, context):
        start = time.perf_counter()
        SCORE_REQUESTS.labels(endpoint="grpc/ScoreDomain", tenant_id=request.tenant_id or "default").inc()

        try:
            with SCORE_LATENCY.labels(model_version=self.scorer.binary.version).time():
                result = self.scorer.score(request.domain)

            if result.is_dga:
                DGA_HITS.labels(family=result.family or "unknown", severity="MEDIUM").inc()

            latency_ms = (time.perf_counter() - start) * 1000
            return scoring_pb2.ScoreResponse(
                domain=result.domain,
                score=result.score,
                is_dga=result.is_dga,
                family=result.family or "",
                family_confidence=result.family_confidence or 0.0,
                model_version=result.model_version,
                trace_id=request.trace_id,
                latency_ms=latency_ms,
            )
        except Exception as e:
            logger.error("grpc_score_error", domain=request.domain, error=str(e))
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return scoring_pb2.ScoreResponse()

    def ScoreBatch(self, request, context):
        start = time.perf_counter()
        SCORE_REQUESTS.labels(endpoint="grpc/ScoreBatch", tenant_id=request.tenant_id or "default").inc()

        try:
            results = []
            for domain in request.domains:
                with SCORE_LATENCY.labels(model_version=self.scorer.binary.version).time():
                    sr = self.scorer.score(domain)

                if sr.is_dga:
                    DGA_HITS.labels(family=sr.family or "unknown", severity="MEDIUM").inc()

                results.append(scoring_pb2.ScoreResponse(
                    domain=sr.domain,
                    score=sr.score,
                    is_dga=sr.is_dga,
                    family=sr.family or "",
                    family_confidence=sr.family_confidence or 0.0,
                    model_version=sr.model_version,
                    trace_id=request.trace_id,
                ))

            total_latency = (time.perf_counter() - start) * 1000
            return scoring_pb2.BatchScoreResponse(
                results=results,
                trace_id=request.trace_id,
                total_latency_ms=total_latency,
            )
        except Exception as e:
            logger.error("grpc_batch_error", error=str(e))
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return scoring_pb2.BatchScoreResponse()

    def HealthCheck(self, request, context):
        return scoring_pb2.HealthResponse(
            status="serving",
            model_binary_version=self.scorer.binary.version,
            model_multi_version=self.scorer.multi.version,
        )


def start_grpc_server(scorer, port: int | None = None) -> grpc.Server:
    """Start gRPC server in a background thread. Returns the server instance."""
    settings = get_settings()
    port = port or settings.scoring_grpc_port

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    scoring_pb2_grpc.add_ScoringServiceServicer_to_server(
        ScoringServiceImpl(scorer), server
    )
    server.add_insecure_port(f"[::]:{port}")
    server.start()
    logger.info("grpc_server_started", port=port)
    return server
