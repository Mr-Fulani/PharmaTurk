from rest_framework import viewsets, status, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from .models import AIProcessingLog
from .serializers import (
    AIProcessingLogSerializer, 
    AIProcessingDetailSerializer, 
    GenerateContentRequestSerializer
)
from .tasks import process_product_ai_task

class AIProcessingLogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = AIProcessingLog.objects.all()
    serializer_class = AIProcessingLogSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return AIProcessingDetailSerializer
        return AIProcessingLogSerializer

class GenerateContentView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = GenerateContentRequestSerializer(data=request.data)
        if serializer.is_valid():
            product_id = serializer.validated_data['product_id']
            processing_type = serializer.validated_data['processing_type']
            auto_apply = serializer.validated_data['auto_apply']
            
            # Запускаем асинхронную задачу
            task = process_product_ai_task.delay(
                product_id=product_id,
                processing_type=processing_type,
                auto_apply=auto_apply
            )
            
            return Response(
                {
                    'status': 'queued',
                    'task_id': task.id,
                    'message': f'Processing started for product {product_id}'
                },
                status=status.HTTP_202_ACCEPTED
            )
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
