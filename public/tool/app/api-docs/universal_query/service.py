from __future__ import annotations

from copy import deepcopy
from typing import Protocol

from api_docs.catalog import ApiCatalog, CatalogError, EndpointRecord
from api_docs.executor import ApiExecutor
from api_docs.systems.errors import SessionExpiredError


class ExecutionTasks(Protocol):
    def start(self, endpoint_id: str, parameters: dict[str, object]) -> dict[str, object]: ...

    def status(self, task_id: str) -> dict[str, object]: ...


class UniversalQueryError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class UniversalQueryService:
    """把当前 Catalog 投影为面向机器人和命令行的安全执行契约。"""

    def __init__(
        self,
        catalog: ApiCatalog,
        executor: ApiExecutor,
        execution_tasks: ExecutionTasks,
    ) -> None:
        self.catalog = catalog
        self.executor = executor
        self.execution_tasks = execution_tasks

    def health(self) -> dict[str, object]:
        return {
            "ok": True,
            "service": "universal-query",
            "version": "v1",
            "systems": [
                {"systemId": system_id, "name": str(system.get("name") or system_id)}
                for system_id, system in self.catalog.systems.items()
            ],
        }

    def sessions(self) -> dict[str, object]:
        return {
            "ok": True,
            "sessions": {
                system_id: self._session(system_id)
                for system_id in self.catalog.systems
            },
        }

    def load_session(self, system_id: str, credential: object) -> dict[str, object]:
        self._require_system(system_id)
        if not isinstance(credential, str) or not credential.strip():
            raise UniversalQueryError("credential_required", "请提供完整 Cookie Header 或 Copy as cURL")
        try:
            self.executor.load_credentials(credential, system_id)
        except Exception as error:
            raise self._execution_error(error, "credential_invalid", "凭据验证失败") from error
        return {"ok": True, "session": self._session(system_id)}

    def clear_session(self, system_id: str) -> dict[str, object]:
        self._require_system(system_id)
        try:
            self.executor.clear_credentials(system_id)
        except Exception as error:
            raise self._execution_error(error, "session_clear_failed", "会话清除失败") from error
        return {"ok": True, "session": self._session(system_id)}

    def operations(self) -> dict[str, object]:
        return {
            "ok": True,
            "operations": [self._operation(record) for record in self.catalog.endpoints.values()],
        }

    def options(self, source_id: str) -> dict[str, object]:
        """Expose catalog-backed dynamic options without exposing session details."""
        if not isinstance(source_id, str) or not source_id.strip():
            raise UniversalQueryError("option_source_required", "请提供选项来源")
        try:
            options = self.executor.load_options(source_id.strip())
        except Exception as error:
            raise self._execution_error(error, "options_failed", "动态选项读取失败") from error
        safe_options = []
        for item in options:
            if isinstance(item, dict):
                safe_options.append({str(key): deepcopy(value) for key, value in item.items()})
        return {"ok": True, "source": source_id.strip(), "options": safe_options}

    def operation(self, operation_id: str) -> dict[str, object]:
        return {"ok": True, "operation": self._operation(self._record(operation_id))}

    def execute(self, operation_id: object, parameters: object) -> tuple[dict[str, object], bool]:
        if not isinstance(operation_id, str) or not operation_id.strip():
            raise UniversalQueryError("operation_required", "请提供 operation")
        if not isinstance(parameters, dict):
            raise UniversalQueryError("parameters_invalid", "parameters 必须是 JSON 对象")

        record = self._record(operation_id)
        system_id = str(record.module.get("systemId") or "")
        if not bool(self._session(system_id).get("ready")):
            raise UniversalQueryError("session_not_ready", "请先载入有效 Cookie")
        effective_parameters = self._materialize_parameters(record, parameters)

        if record.endpoint.get("progressive") is True:
            try:
                task = self.execution_tasks.start(record.full_id, effective_parameters)
            except Exception as error:
                raise self._execution_error(error, "execution_start_failed", "无法启动执行任务") from error
            return self._task_envelope(task), True

        try:
            result = self.executor.execute(record.full_id, effective_parameters)
        except Exception as error:
            raise self._execution_error(error, "execution_failed", "操作执行失败") from error
        return self._completed_envelope(record, result), False

    def execution(self, run_id: str) -> dict[str, object]:
        if not run_id:
            raise UniversalQueryError("run_id_required", "请提供 runId")
        try:
            task = self.execution_tasks.status(run_id)
        except Exception as error:
            raise self._execution_error(error, "run_not_found", "执行任务不存在") from error
        return self._task_envelope(task)

    @staticmethod
    def error_response(error: Exception) -> dict[str, object]:
        if isinstance(error, UniversalQueryError):
            return {
                "ok": False,
                "error": {"code": error.code, "message": error.message},
            }
        return {
            "ok": False,
            "error": {"code": "bad_request", "message": "请求无效"},
        }

    def _operation(self, record: EndpointRecord) -> dict[str, object]:
        endpoint = record.endpoint
        parameters = [
            self._parameter(parameter)
            for parameter in endpoint.get("parameters", [])
            if isinstance(parameter, dict)
        ]
        return {
            "operation": record.full_id,
            "name": str(endpoint.get("name") or record.full_id),
            "summary": str(endpoint.get("summary") or ""),
            "module": str(record.module.get("id") or ""),
            "moduleName": str(record.module.get("name") or ""),
            "systemId": str(record.module.get("systemId") or ""),
            "risk": str(endpoint.get("risk") or ""),
            "executionKind": str((endpoint.get("execution") or {}).get("kind") or ""),
            "progressive": endpoint.get("progressive") is True,
            "parameters": parameters,
            "minimumInput": [
                str(parameter["name"])
                for parameter in parameters
                if parameter["callerRequired"] is True
            ],
        }

    @staticmethod
    def _parameter(source: dict[str, object]) -> dict[str, object]:
        automatic = source.get("auto")
        fixed = source.get("fixed") is True
        mode = "automatic" if automatic else "fixed" if fixed else "input"
        has_default = "default" in source and UniversalQueryService._has_value(source.get("default"))
        required = source.get("required") is True
        result: dict[str, object] = {
            "name": str(source.get("name") or ""),
            "label": str(source.get("label") or source.get("name") or ""),
            "location": str(source.get("in") or ""),
            "type": str(source.get("type") or "text"),
            "mode": mode,
            "required": required,
            "callerRequired": mode == "input" and required and not has_default,
            "repeatable": source.get("repeatable") is True,
        }
        for key in (
            "default",
            "auto",
            "description",
            "placeholder",
            "minimum",
            "maximum",
            "maxlength",
            "options",
            "optionSource",
        ):
            if key in source:
                result[key] = deepcopy(source[key])
        return result

    def _materialize_parameters(
        self,
        record: EndpointRecord,
        supplied: dict[str, object],
    ) -> dict[str, object]:
        definitions = [
            parameter
            for parameter in record.endpoint.get("parameters", [])
            if isinstance(parameter, dict)
        ]
        defined_names = {str(parameter.get("name") or "") for parameter in definitions}
        unknown = sorted(str(name) for name in supplied if str(name) not in defined_names)
        if unknown:
            raise UniversalQueryError("parameter_unknown", f"未定义参数：{', '.join(unknown)}")

        effective: dict[str, object] = {}
        for definition in definitions:
            name = str(definition.get("name") or "")
            mode = self._parameter(definition)["mode"]
            if mode != "input":
                if name in supplied:
                    raise UniversalQueryError("parameter_managed", f"参数由服务管理：{name}")
                continue
            if name in supplied:
                value = supplied[name]
            elif "default" in definition:
                value = deepcopy(definition["default"])
            else:
                value = None
            if definition.get("required") is True and not self._has_value(value):
                label = str(definition.get("label") or name)
                raise UniversalQueryError("parameter_required", f"请提供{label}")
            if value is not None:
                effective[name] = value
        return effective

    def _completed_envelope(self, record: EndpointRecord, result: object) -> dict[str, object]:
        return {
            "ok": True,
            "operation": record.full_id,
            "systemId": str(record.module.get("systemId") or ""),
            "risk": str(record.endpoint.get("risk") or ""),
            "state": "completed",
            "result": self._result(result),
        }

    def _task_envelope(self, task: dict[str, object]) -> dict[str, object]:
        endpoint_id = str(task.get("endpointId") or "")
        record = self._record(endpoint_id)
        state = str(task.get("state") or "failed")
        run_id = str(task.get("taskId") or "")
        if state == "failed":
            return {
                "ok": False,
                "operation": record.full_id,
                "systemId": str(record.module.get("systemId") or ""),
                "risk": str(record.endpoint.get("risk") or ""),
                "state": "failed",
                "runId": run_id,
                "error": {"code": "execution_failed", "message": "操作执行失败"},
            }
        return {
            "ok": True,
            "operation": record.full_id,
            "systemId": str(record.module.get("systemId") or ""),
            "risk": str(record.endpoint.get("risk") or ""),
            "state": state,
            "runId": run_id,
            "result": self._result(task.get("result")),
        }

    @staticmethod
    def _result(source: object) -> dict[str, object] | None:
        if not isinstance(source, dict):
            return None
        data = source.get("data")
        if not isinstance(data, dict):
            data = {}
        summary = data.get("summary")
        tables = data.get("tables")
        return {
            "meta": {
                key: deepcopy(source[key])
                for key in ("status", "reason", "elapsedMilliseconds", "contentType", "method")
                if key in source
            },
            "summary": deepcopy(summary) if summary is not None else {},
            "tables": deepcopy(tables) if isinstance(tables, list) else [],
        }

    def _session(self, system_id: str) -> dict[str, object]:
        self._require_system(system_id)
        all_statuses = self.executor.all_session_statuses()
        raw = all_statuses.get(system_id, {})
        raw = raw if isinstance(raw, dict) else {}
        keepalive = raw.get("keepAlive")
        keepalive = keepalive if isinstance(keepalive, dict) else {}
        cookie_count = self._cookie_count(raw.get("cookieCount"))
        return {
            "systemId": system_id,
            "ready": raw.get("ready") is True or cookie_count > 0,
            "identity": deepcopy(raw.get("identity")) if raw.get("identity") is not None else None,
            "cookieNames": deepcopy(raw.get("cookieNames")) if isinstance(raw.get("cookieNames"), list) else [],
            "cookieCount": cookie_count,
            "keepAlive": {
                key: deepcopy(keepalive[key])
                for key in ("state", "running", "lastCheckedAt", "nextIntervalSeconds", "error")
                if key in keepalive
            },
        }

    def _record(self, operation_id: str) -> EndpointRecord:
        try:
            return self.catalog.get_endpoint(operation_id)
        except CatalogError as error:
            raise UniversalQueryError("operation_not_found", "操作不存在") from error

    def _require_system(self, system_id: str) -> None:
        if system_id not in self.catalog.systems:
            raise UniversalQueryError("system_not_found", "业务系统不存在")

    @staticmethod
    def _has_value(value: object) -> bool:
        if value is None:
            return False
        if isinstance(value, str):
            return bool(value.strip())
        if isinstance(value, (list, tuple, dict)):
            return bool(value)
        return True

    @staticmethod
    def _cookie_count(value: object) -> int:
        try:
            return max(0, int(value or 0))
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _execution_error(error: Exception, code: str, message: str) -> UniversalQueryError:
        if isinstance(error, UniversalQueryError):
            return error
        if isinstance(error, SessionExpiredError):
            return UniversalQueryError("session_expired", "会话已失效，请重新载入 Cookie")
        return UniversalQueryError(code, message)
