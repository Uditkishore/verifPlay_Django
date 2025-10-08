from rest_framework import serializers

class CircuitFileUploadSerializer(serializers.Serializer):
    file = serializers.FileField(required=True, help_text="Excel file with circuit data")
    
    def validate_file(self, value):
        """Validate the uploaded file"""
        if not value.name.endswith(('.xlsx', '.xls')):
            raise serializers.ValidationError("File must be an Excel file (.xlsx or .xls)")
        
        # Check file size (10MB limit)
        if value.size > 10 * 1024 * 1024:
            raise serializers.ValidationError("File size must be less than 10MB")
        
        return value