from rest_framework import serializers
from core.models import EventType, EventTypeWorkingHour, EventTypeSubAccountMapping, SubAccount, Workspace


class EventTypeWorkingHourSerializer(serializers.ModelSerializer):
    class Meta:
        model = EventTypeWorkingHour
        fields = [
            'day_of_week',
            'start_time',
            'end_time',
        ]


class EventTypeCalendarMappingSerializer(serializers.Serializer):
    sub_account_id = serializers.UUIDField()
    role = serializers.ChoiceField(choices=[('target', 'target'), ('conflict', 'conflict')])


class EventTypeCreateUpdateSerializer(serializers.ModelSerializer):
    working_hours = EventTypeWorkingHourSerializer(many=True, required=False)
    calendar_mappings = EventTypeCalendarMappingSerializer(many=True, required=True)

    class Meta:
        model = EventType
        fields = [
            'id',
            'name',
            'duration',
            'timezone',
            'buffer_time',
            'prep_time',
            'working_hours',
            'calendar_mappings',
        ]
        read_only_fields = ['id']

    def validate(self, attrs):
        mappings = attrs.get('calendar_mappings') or []
        if not mappings:
            raise serializers.ValidationError({'calendar_mappings': 'At least one calendar mapping is required'})

        # Require at least one target
        targets = [m for m in mappings if m.get('role') == 'target']
        if len(targets) < 1:
            raise serializers.ValidationError({'calendar_mappings': 'At least one target mapping is required'})

        # Validate subaccounts exist and belong to same workspace via owner membership
        request = self.context.get('request')
        workspace: Workspace = self.context.get('workspace')
        if not request or not workspace:
            raise serializers.ValidationError('Workspace context missing')

        sub_ids = [str(m['sub_account_id']) for m in mappings]
        # Ensure uniqueness within payload
        if len(sub_ids) != len(set(sub_ids)):
            raise serializers.ValidationError({'calendar_mappings': 'Duplicate sub_account_id in payload'})

        sub_qs = SubAccount.objects.filter(id__in=sub_ids)
        if sub_qs.count() != len(sub_ids):
            raise serializers.ValidationError({'calendar_mappings': 'One or more sub_account_id not found'})

        # Owners of subaccounts must be members of the workspace
        member_ids = set(workspace.users.values_list('id', flat=True))
        for sub in sub_qs:
            if sub.owner_id not in member_ids:
                raise serializers.ValidationError({'calendar_mappings': 'Sub-account owner must be a member of the workspace'})

        # Validate working hours: enforce at most one interval per weekday
        hours = attrs.get('working_hours') or []
        seen_days = set()
        for wh in hours:
            day = wh['day_of_week']
            if day in seen_days:
                raise serializers.ValidationError({'working_hours': 'Only one interval per weekday is allowed'})
            seen_days.add(day)

        return attrs

    def create(self, validated_data):
        working_hours = validated_data.pop('working_hours', [])
        calendar_mappings = validated_data.pop('calendar_mappings', [])

        request = self.context['request']
        workspace: Workspace = self.context['workspace']

        et = EventType.objects.create(
            workspace=workspace,
            created_by=request.user if request and request.user.is_authenticated else None,
            **validated_data,
        )

        # Create working hours
        wh_objects = [
            EventTypeWorkingHour(event_type=et, **wh)
            for wh in (working_hours or [])
        ]
        if wh_objects:
            EventTypeWorkingHour.objects.bulk_create(wh_objects)

        # Link calendar mappings
        for m in calendar_mappings:
            sub = SubAccount.objects.get(id=m['sub_account_id'])
            EventTypeSubAccountMapping.objects.create(event_type=et, sub_account=sub, role=m['role'])

        return et

    def update(self, instance: EventType, validated_data):
        working_hours = validated_data.pop('working_hours', None)
        calendar_mappings = validated_data.pop('calendar_mappings', None)

        for attr, val in validated_data.items():
            setattr(instance, attr, val)
        instance.save()

        if working_hours is not None:
            # Replace working hours
            EventTypeWorkingHour.objects.filter(event_type=instance).delete()
            wh_objects = [EventTypeWorkingHour(event_type=instance, **wh) for wh in working_hours]
            if wh_objects:
                EventTypeWorkingHour.objects.bulk_create(wh_objects)

        if calendar_mappings is not None:
            # Replace mappings
            EventTypeSubAccountMapping.objects.filter(event_type=instance).delete()
            for m in calendar_mappings:
                sub = SubAccount.objects.get(id=m['sub_account_id'])
                EventTypeSubAccountMapping.objects.create(event_type=instance, sub_account=sub, role=m['role'])

        return instance


class EventTypeSerializer(serializers.ModelSerializer):
    working_hours = EventTypeWorkingHourSerializer(many=True, read_only=True)
    calendar_mappings = serializers.SerializerMethodField()

    class Meta:
        model = EventType
        fields = [
            'id', 'workspace', 'created_by', 'name', 'duration', 'timezone',
            'buffer_time', 'prep_time', 'working_hours', 'calendar_mappings',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'workspace', 'created_by', 'created_at', 'updated_at']

    def get_calendar_mappings(self, obj: EventType):
        mappings = obj.calendar_mappings.select_related('sub_account').all()
        return [
            {
                'sub_account_id': str(m.sub_account_id),
                'role': m.role,
                'provider': m.sub_account.provider,
            }
            for m in mappings
        ]


class SubAccountListItemSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    provider = serializers.ChoiceField(choices=[('google', 'google'), ('outlook', 'outlook')])
    label = serializers.CharField()


