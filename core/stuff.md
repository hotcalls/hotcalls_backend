Based on the last test run output, here are ALL the failing tests:
ERRORS (9 tests):
test_negative_limit_value - KeyError: 'limit'
test_very_large_limit_value - KeyError: 'limit'
test_zero_limit_value - KeyError: 'limit'
FAILURES (66 tests):
Agent API (10 failures):
test_agent_with_all_weekdays - Expected 403, got 201
test_agent_with_very_long_text_fields - String comparison mismatch
test_assign_duplicate_phone_numbers - Missing 'already_assigned' field
test_assign_nonexistent_phone_numbers - Expected 200, got 400
test_create_agent_validation - Expected 400, got 201 (invalid workdays accepted)
test_create_agent_with_config_id - Expected 403, got 201
test_get_config_with_phone_numbers - Expected string, got dict object
test_remove_unassigned_phone_numbers - Missing 'not_assigned' field
test_update_agent_as_admin - 415 Unsupported media type (missing format='json')
test_update_agent_times - 415 Unsupported media type (missing format='json')
Calendar API (23 failures):
test_calendar_types - Expected 403, got 201
test_calendar_with_long_auth_token - Expected 403, got 201
test_cannot_change_calendar_type - Expected 403, got 200
test_check_availability_as_admin - Expected 403, got 200
test_check_availability_validation - Expected 201, got 400
test_check_availability_with_buffer - Expected 403, got 200
test_configuration_24_hour_availability - Expected 403, got 201
test_configuration_duration_edge_cases - Expected 403, got 201
test_configuration_with_all_weekdays - Expected 403, got 201
test_configuration_with_overnight_hours - Expected 403, got 201
test_create_calendar_validation - Expected 403, got 400
test_create_calendar_without_workspace - Expected 403, got 201
test_create_configuration_validation - Expected 403, got 400
test_create_duplicate_calendar - Expected 201, got 400
test_get_calendar_configurations - Expected 403, got 200
test_get_configurations_empty_calendar - Expected 403, got 200
test_list_calendars_with_filters - UUID vs string comparison
test_multiple_calendars_same_account - Expected 403, got 201
test_update_calendar_configuration - Expected 403, got 200
Call API (8 failures):
test_analytics_by_direction - 'outbound_calls' not found in {}
test_call_log_with_same_numbers - Expected 403, got 201
test_create_call_log_validation - Expected 400, got 201 (negative duration accepted)
test_create_call_log_without_disconnection_reason - Expected 403, got 201
test_daily_stats_as_regular_user - Expected 403, got 200
test_daily_stats_empty_days - Expected 0 calls, got 1
test_delete_call_log_as_regular_user - Expected 200, got 403
test_duration_distribution_as_regular_user - Expected 403, got 200
test_get_call_analytics_as_admin - 'total_calls' not found in {}
test_get_daily_stats_as_admin - Date sorting issue
test_list_call_logs_unauthenticated - Expected 200, got 403
Subscription API (10 failures):
test_cascade_delete_feature - Expected 200, got 204
test_cascade_delete_plan - Expected 200, got 204
test_create_duplicate_feature - Expected 403, got 400
test_create_duplicate_plan - Expected 403, got 400
test_create_plan_feature_directly - Expected 200, got 201
test_create_plan_validation - Expected 403, got 400
test_delete_plan_as_regular_user - Expected 200, got 403
test_plan_name_with_special_characters - Expected 200, got 201
test_remove_feature_from_plan_as_admin - Expected 200, got 204
test_update_plan_as_regular_user - Expected 200, got 403
test_very_long_plan_name - Expected 403, got 400
Workspace API (15 failures):
test_add_duplicate_users_to_workspace - Missing 'already_members' field
test_add_nonexistent_users - Expected 200, got 400
test_add_users_mixed_results - Expected 200, got 400
test_create_workspace_with_users - Expected 403, got 201
test_get_stats_empty_workspace - Expected 200, got 404
test_get_users_empty_workspace - Expected 200, got 404
test_get_workspace_stats - 'workspace_name' not found in {}
test_list_workspaces_unauthenticated - Expected 200, got 403
test_list_workspaces_with_ordering - Wrong workspace order
test_list_workspaces_with_search - Count 0, expected >= 1
test_pagination_users_list - Expected 200, got 404
test_remove_nonexistent_users - Expected 200, got 400
test_remove_users_not_in_workspace - Missing 'not_members' field
test_update_workspace_as_regular_user - Expected 200, got 403
test_workspace_name_with_special_characters - Expected 403, got 201