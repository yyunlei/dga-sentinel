"""
Auto-generated-style gRPC stubs for scoring.proto
In production, regenerate with: bash compile.sh
"""
import grpc
from ai.scoring.proto import scoring_pb2 as scoring__pb2


class ScoringServiceServicer:
    """Base class for ScoringService servicer."""

    def ScoreDomain(self, request, context):
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details("Method not implemented!")
        raise NotImplementedError("Method not implemented!")

    def ScoreBatch(self, request, context):
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details("Method not implemented!")
        raise NotImplementedError("Method not implemented!")

    def HealthCheck(self, request, context):
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details("Method not implemented!")
        raise NotImplementedError("Method not implemented!")


def add_ScoringServiceServicer_to_server(servicer, server):
    """Register servicer with gRPC server using method handlers."""
    from grpc import unary_unary_rpc_method_handler

    rpc_method_handlers = {
        "ScoreDomain": unary_unary_rpc_method_handler(servicer.ScoreDomain),
        "ScoreBatch": unary_unary_rpc_method_handler(servicer.ScoreBatch),
        "HealthCheck": unary_unary_rpc_method_handler(servicer.HealthCheck),
    }
    # For grpcio >= 1.60, use method_handlers_generic_handler
    # For older versions, use method_service_handler (deprecated)
    if hasattr(grpc, 'method_handlers_generic_handler'):
        # New API for grpcio >= 1.60
        generic_handler = grpc.method_handlers_generic_handler(
            "dga.scoring.ScoringService", rpc_method_handlers
        )
    elif hasattr(grpc, 'method_service_handler'):
        # Old API for grpcio < 1.60 (deprecated but still works)
        generic_handler = grpc.method_service_handler(
            "dga.scoring.ScoringService", rpc_method_handlers
        )
    else:
        raise RuntimeError(
            "Unsupported grpcio version. Please upgrade to grpcio >= 1.60 "
            "or regenerate proto files with compatible grpcio-tools version."
        )
    server.add_generic_rpc_handlers((generic_handler,))
