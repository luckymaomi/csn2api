from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


SCHEMA_VERSION = 2
EXECUTION_KINDS = {"direct-http", "local-workflow"}
STEP_ROLES = {"primary", "prerequisite", "page-loop", "item-loop", "postcondition"}
CARDINALITIES = {"once", "zero-or-one", "one-or-more", "zero-or-more"}
RELATED_KINDS = {"metadata", "option-source", "export", "reference-query", "state-action"}
RISKS = {"read", "write"}


class CatalogError(ValueError):
    pass


@dataclass(frozen=True)
class EndpointRecord:
    full_id: str
    module: dict[str, object]
    endpoint: dict[str, object]

    @property
    def url(self) -> str:
        return f"{str(self.module['baseUrl']).rstrip('/')}{self.endpoint['path']}"


class ApiCatalog:
    def __init__(self, catalog_directory: Path):
        self.catalog_directory = catalog_directory.resolve()
        self.data = self._load()
        self.modules = self._index_modules()
        self.systems = self._index_systems()
        self.endpoints = self._index_endpoints()
        self.request_definitions = self._index_request_definitions()
        self.related_requests: dict[str, list[dict[str, object]]] = {}
        self.option_sources: dict[str, EndpointRecord] = {}
        self._validate_request_roles()

    @staticmethod
    def _read_json(path: Path) -> dict[str, object]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise CatalogError(f"无法读取接口目录：{path.name}") from error
        if not isinstance(value, dict):
            raise CatalogError(f"接口目录必须是 JSON 对象：{path.name}")
        return value

    @staticmethod
    def _https_url(value: object, label: str) -> None:
        parsed = urlparse(str(value or ""))
        if parsed.scheme != "https" or not parsed.netloc:
            raise CatalogError(f"{label}无效")

    def _load(self) -> dict[str, object]:
        index = self._read_json(self.catalog_directory / "index.json")
        if (
            index.get("schemaVersion") != SCHEMA_VERSION
            or not isinstance(index.get("systems"), list)
            or not isinstance(index.get("modules"), list)
        ):
            raise CatalogError("接口目录索引格式无效")

        systems: list[dict[str, object]] = []
        system_ids: set[str] = set()
        for system in index["systems"]:
            if not isinstance(system, dict):
                raise CatalogError("系统目录格式无效")
            if "validationRequestId" in system:
                raise CatalogError("系统目录仍包含旧会话字段")
            system_id = str(system.get("id", ""))
            if not system_id or system_id in system_ids:
                raise CatalogError("系统 ID 缺失或重复")
            self._https_url(system.get("navigationUrl"), f"系统网址：{system_id}")
            self._https_url(system.get("credentialRequestUrl"), f"凭据请求网址：{system_id}")
            if not isinstance(system.get("credentialSteps"), list):
                raise CatalogError(f"Cookie 获取步骤无效：{system_id}")
            session = system.get("session")
            if not isinstance(session, dict):
                raise CatalogError(f"系统会话契约无效：{system_id}")
            for field in ("validationRequestRef", "identityRequestRef", "keepAliveRequestRef"):
                if not str(session.get(field, "")):
                    raise CatalogError(f"系统会话请求缺失：{system_id}.{field}")
            system_ids.add(system_id)
            systems.append(system)

        modules: list[dict[str, object]] = []
        for item in index["modules"]:
            if not isinstance(item, dict):
                raise CatalogError("接口模块索引格式无效")
            source = str(item.get("source", ""))
            source_path = (self.catalog_directory / source).resolve()
            try:
                source_path.relative_to(self.catalog_directory)
            except ValueError as error:
                raise CatalogError("接口模块路径超出目录") from error
            module = self._read_json(source_path)
            if module.get("schemaVersion") != SCHEMA_VERSION or module.get("id") != item.get("id"):
                raise CatalogError(f"接口模块标识不一致：{source}")
            if "internalRequests" in module:
                raise CatalogError(f"接口模块仍包含旧请求字段：{source}")
            if str(module.get("systemId", "")) not in system_ids:
                raise CatalogError(f"接口模块所属系统不存在：{source}")
            self._materialize_endpoint_defaults(module)
            modules.append(module)
        return {"schemaVersion": SCHEMA_VERSION, "systems": systems, "modules": modules}

    @staticmethod
    def _materialize_endpoint_defaults(module: dict[str, object]) -> None:
        defaults = module.get("endpointDefaults", {})
        common_parameters = module.get("commonParameters", [])
        if not isinstance(defaults, dict) or not isinstance(common_parameters, list):
            raise CatalogError("接口模块共享契约格式无效")
        endpoints = module.get("endpoints", [])
        if not isinstance(endpoints, list):
            raise CatalogError("接口列表格式无效")
        expanded: list[object] = []
        for endpoint in endpoints:
            if not isinstance(endpoint, dict):
                expanded.append(endpoint)
                continue
            merged = {**deepcopy(defaults), **endpoint}
            own_parameters = endpoint.get("parameters", [])
            if not isinstance(own_parameters, list):
                expanded.append(merged)
                continue
            names = {
                str(parameter.get("name", ""))
                for parameter in own_parameters
                if isinstance(parameter, dict)
            }
            merged["parameters"] = [
                *deepcopy(own_parameters),
                *(
                    deepcopy(parameter)
                    for parameter in common_parameters
                    if not isinstance(parameter, dict) or str(parameter.get("name", "")) not in names
                ),
            ]
            expanded.append(merged)
        module["endpoints"] = expanded

    def _index_modules(self) -> dict[str, dict[str, object]]:
        indexed: dict[str, dict[str, object]] = {}
        for module in self.data["modules"]:
            if not isinstance(module, dict):
                raise CatalogError("接口模块格式无效")
            module_id = str(module.get("id", ""))
            if not module_id or module_id in indexed:
                raise CatalogError("接口模块 ID 缺失或重复")
            self._https_url(module.get("baseUrl"), f"接口模块基础地址：{module_id}")
            self._https_url(module.get("navigationUrl"), f"接口模块导航地址：{module_id}")
            indexed[module_id] = module
        return indexed

    def _index_systems(self) -> dict[str, dict[str, object]]:
        return {
            str(system["id"]): system
            for system in self.data["systems"]
            if isinstance(system, dict)
        }

    @staticmethod
    def _validate_parameters(parameters: object, full_id: str) -> None:
        if not isinstance(parameters, list):
            raise CatalogError(f"接口参数格式无效：{full_id}")
        names: set[str] = set()
        for parameter in parameters:
            if not isinstance(parameter, dict):
                raise CatalogError(f"接口参数格式无效：{full_id}")
            name = str(parameter.get("name", ""))
            if not name or name in names or parameter.get("in") not in {"query", "form", "json", "workflow"}:
                raise CatalogError(f"接口参数名称或位置无效：{full_id}")
            names.add(name)

    def _index_endpoints(self) -> dict[str, EndpointRecord]:
        indexed: dict[str, EndpointRecord] = {}
        for module_id, module in self.modules.items():
            groups = module.get("groups", [])
            if not isinstance(groups, list):
                raise CatalogError(f"接口分组格式无效：{module_id}")
            group_ids = {
                str(group.get("id", ""))
                for group in groups
                if isinstance(group, dict) and group.get("id")
            }
            endpoints = module.get("endpoints", [])
            if not isinstance(endpoints, list):
                raise CatalogError(f"接口列表格式无效：{module_id}")
            for endpoint in endpoints:
                if not isinstance(endpoint, dict):
                    raise CatalogError(f"接口定义格式无效：{module_id}")
                if "executionKind" in endpoint:
                    raise CatalogError(f"接口仍包含旧执行字段：{module_id}")
                endpoint_id = str(endpoint.get("id", ""))
                full_id = f"{module_id}.{endpoint_id}"
                if not endpoint_id or full_id in indexed:
                    raise CatalogError("接口 ID 缺失或重复")
                if str(endpoint.get("groupId", "")) not in group_ids:
                    raise CatalogError(f"接口分组不存在：{full_id}")
                if endpoint.get("risk") not in RISKS:
                    raise CatalogError(f"接口风险无效：{full_id}")
                if endpoint.get("method") not in {"GET", "POST"}:
                    raise CatalogError(f"接口方法无效：{full_id}")
                if not str(endpoint.get("path", "")).startswith("/"):
                    raise CatalogError(f"接口路径无效：{full_id}")
                self._validate_parameters(endpoint.get("parameters", []), full_id)
                indexed[full_id] = EndpointRecord(full_id, module, endpoint)
        if not indexed:
            raise CatalogError("接口目录没有可用接口")
        return indexed

    def _index_request_definitions(self) -> dict[str, EndpointRecord]:
        indexed: dict[str, EndpointRecord] = {}
        for module_id, module in self.modules.items():
            definitions = module.get("requestDefinitions", [])
            if not isinstance(definitions, list):
                raise CatalogError(f"请求定义列表格式无效：{module_id}")
            for request in definitions:
                if not isinstance(request, dict):
                    raise CatalogError(f"请求定义格式无效：{module_id}")
                request_id = str(request.get("id", ""))
                full_id = f"{module_id}.{request_id}"
                if not request_id or full_id in indexed:
                    raise CatalogError("请求定义 ID 缺失或重复")
                if not all(str(request.get(field, "")).strip() for field in ("name", "purpose", "response")):
                    raise CatalogError(f"请求定义说明缺失：{full_id}")
                if request.get("risk") not in RISKS:
                    raise CatalogError(f"请求定义风险无效：{full_id}")
                if request.get("method") not in {"GET", "POST"}:
                    raise CatalogError(f"请求定义方法无效：{full_id}")
                if not str(request.get("path", "")).startswith("/"):
                    raise CatalogError(f"请求定义路径无效：{full_id}")
                if not isinstance(request.get("parameters"), list):
                    raise CatalogError(f"请求定义参数格式无效：{full_id}")
                if not isinstance(request.get("headers", []), list):
                    raise CatalogError(f"请求定义 Headers 格式无效：{full_id}")
                indexed[full_id] = EndpointRecord(full_id, module, request)
        return indexed

    def _request_for_reference(self, request_ref: object) -> EndpointRecord:
        reference = str(request_ref or "")
        try:
            return self.request_definitions[reference]
        except KeyError as error:
            raise CatalogError(f"请求引用不存在：{reference}") from error

    @staticmethod
    def _same_system(source_system: str, record: EndpointRecord, label: str) -> None:
        if str(record.module.get("systemId", "")) != source_system:
            raise CatalogError(f"请求引用跨系统：{label}")

    def _validate_request_roles(self) -> None:
        used: set[str] = set()
        for system_id, system in self.systems.items():
            session = system["session"]
            assert isinstance(session, dict)
            for field in ("validationRequestRef", "identityRequestRef", "keepAliveRequestRef"):
                request = self._request_for_reference(session[field])
                self._same_system(system_id, request, f"{system_id}.{field}")
                used.add(request.full_id)

        for endpoint_id, record in self.endpoints.items():
            execution = record.endpoint.get("execution")
            if not isinstance(execution, dict) or execution.get("kind") not in EXECUTION_KINDS:
                raise CatalogError(f"接口执行契约无效：{endpoint_id}")
            kind = str(execution["kind"])
            steps = execution.get("steps")
            if not isinstance(steps, list) or not steps:
                raise CatalogError(f"接口执行步骤缺失：{endpoint_id}")
            step_ids: set[str] = set()
            own_primary = 0
            for step in steps:
                if not isinstance(step, dict):
                    raise CatalogError(f"接口执行步骤格式无效：{endpoint_id}")
                step_id = str(step.get("id", ""))
                request_ref = str(step.get("requestRef", ""))
                role = str(step.get("role", ""))
                cardinality = str(step.get("cardinality", ""))
                if not step_id or step_id in step_ids:
                    raise CatalogError(f"接口执行步骤 ID 缺失或重复：{endpoint_id}")
                if role not in STEP_ROLES or cardinality not in CARDINALITIES:
                    raise CatalogError(f"接口执行步骤角色或次数无效：{endpoint_id}.{step_id}")
                if cardinality == "zero-or-one" and not str(step.get("condition", "")).strip():
                    raise CatalogError(f"条件执行步骤缺少条件：{endpoint_id}.{step_id}")
                if role in {"page-loop", "item-loop"} and not str(step.get("stopCondition", "")).strip():
                    raise CatalogError(f"循环执行步骤缺少停止条件：{endpoint_id}.{step_id}")
                if request_ref == "$endpoint":
                    if kind != "direct-http" or role != "primary" or cardinality != "once":
                        raise CatalogError(f"端点自身请求角色无效：{endpoint_id}.{step_id}")
                    own_primary += 1
                else:
                    request = self._request_for_reference(request_ref)
                    self._same_system(str(record.module["systemId"]), request, f"{endpoint_id}.{step_id}")
                    used.add(request.full_id)
                step_ids.add(step_id)
            if kind == "direct-http" and own_primary != 1:
                raise CatalogError(f"直接接口必须且只能声明一个自身主请求：{endpoint_id}")
            if kind == "local-workflow" and own_primary:
                raise CatalogError(f"本地工作流不能把本地端点声明为生产请求：{endpoint_id}")

        source_ids: set[str] = set()
        for module_id, module in self.modules.items():
            relations = module.get("relatedRequests", [])
            if not isinstance(relations, list):
                raise CatalogError(f"模块相关请求格式无效：{module_id}")
            normalized: list[dict[str, object]] = []
            for relation in relations:
                if not isinstance(relation, dict):
                    raise CatalogError(f"模块相关请求格式无效：{module_id}")
                kind = str(relation.get("kind", ""))
                request_ref = str(relation.get("requestRef", ""))
                if kind not in RELATED_KINDS or not str(relation.get("description", "")).strip():
                    raise CatalogError(f"模块相关请求角色无效：{module_id}")
                request = self._request_for_reference(request_ref)
                self._same_system(str(module["systemId"]), request, f"{module_id}.{request_ref}")
                if kind == "state-action" and request.endpoint.get("risk") != "write":
                    raise CatalogError(f"状态动作未标记写风险：{request_ref}")
                source_id = str(relation.get("sourceId", ""))
                if kind == "option-source":
                    if not source_id or source_id in source_ids:
                        raise CatalogError(f"动态选项来源 ID 缺失或重复：{module_id}")
                    source_ids.add(source_id)
                    self.option_sources[source_id] = request
                elif source_id:
                    raise CatalogError(f"非选项请求不能声明 sourceId：{request_ref}")
                used.add(request.full_id)
                normalized.append(relation)
            self.related_requests[module_id] = normalized

        orphaned = sorted(set(self.request_definitions) - used)
        if orphaned:
            raise CatalogError(f"请求定义没有使用方：{', '.join(orphaned)}")

    def get_endpoint(self, endpoint_id: str) -> EndpointRecord:
        try:
            return self.endpoints[endpoint_id]
        except KeyError as error:
            raise CatalogError("接口不存在") from error

    def get_request_definition(self, request_ref: str) -> EndpointRecord:
        return self._request_for_reference(request_ref)

    def get_session_request(self, system_id: str, purpose: str) -> EndpointRecord:
        fields = {
            "validation": "validationRequestRef",
            "identity": "identityRequestRef",
            "keepAlive": "keepAliveRequestRef",
        }
        if purpose not in fields:
            raise CatalogError("系统会话请求用途无效")
        try:
            system = self.systems[system_id]
        except KeyError as error:
            raise CatalogError("系统不存在") from error
        session = system["session"]
        assert isinstance(session, dict)
        return self._request_for_reference(session[fields[purpose]])

    def get_execution_steps(self, endpoint_id: str) -> list[dict[str, object]]:
        endpoint = self.get_endpoint(endpoint_id).endpoint
        execution = endpoint["execution"]
        assert isinstance(execution, dict)
        steps = execution["steps"]
        assert isinstance(steps, list)
        return [step for step in steps if isinstance(step, dict)]

    def get_execution_request(self, endpoint_id: str, step_id: str) -> EndpointRecord:
        record = self.get_endpoint(endpoint_id)
        step = next(
            (item for item in self.get_execution_steps(endpoint_id) if item.get("id") == step_id),
            None,
        )
        if step is None:
            raise CatalogError("接口执行步骤不存在")
        if step.get("requestRef") == "$endpoint":
            return record
        return self._request_for_reference(step.get("requestRef"))

    def get_related_requests(self, module_id: str) -> list[dict[str, object]]:
        if module_id not in self.modules:
            raise CatalogError("接口模块不存在")
        return list(self.related_requests[module_id])

    def get_option_source(self, source_id: str) -> EndpointRecord:
        try:
            return self.option_sources[source_id]
        except KeyError as error:
            raise CatalogError("动态选项来源不存在") from error

    def as_dict(self) -> dict[str, object]:
        return self.data
