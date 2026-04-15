## PR Review -- `amrtdemdevteam/AMR_gen3_robot_gateway` #4


### 📄 `.gitignore`


### 📄 `Dockerfile`

#### 🟠 High — Unpinned latest base image breaks reproducibility

Using a mutable `:latest` tag makes the build non-deterministic and can silently pull incompatible ROS/runtime changes. For a robot gateway, this is a reliability and safety risk because rebuilt images may behave differently in production without any source change, and it also weakens supply-chain control.

**Suggestion:** Pin the base image to an immutable version or digest so builds are reproducible and auditable.

```suggestion
FROM ros2-jazzy-gen3-interfaces@sha256:<pinned-image-digest>
```

---

#### 🟠 High — Removed ROS entrypoint breaks runtime environment

The diff deletes the image entrypoint and does not replace it. Without sourcing the ROS environment at container startup, runtime commands, overlays, and package discovery can fail when the container is launched with a custom command. This is a major reliability issue for ROS-based services because build-time sourcing does not persist into runtime containers.

**Suggestion:** Restore a runtime entrypoint that sources ROS before executing the container command. If the base image already provides `/ros_entrypoint.sh`, explicitly use it after the build step.

```suggestion
RUN bash -c ". /opt/ros/jazzy/setup.bash && colcon build"

ENTRYPOINT ["/ros_entrypoint.sh"]
```

---

#### 🟠 High — Pip install is unpinned and bypasses system package protections

Installing `pydantic`, `fastapi`, `uvicorn`, `pyyaml`, and `slowapi` with open-ended version ranges and `--break-system-packages` creates a high-risk dependency state. Future upstream releases can introduce breaking API changes or vulnerabilities, and overriding system-managed packages can destabilize the ROS Python environment. In a gateway exposed over HTTP/WebSockets, this directly impacts security and runtime reliability.

**Suggestion:** Pin exact package versions and avoid breaking system packages unless absolutely required. Prefer a virtual environment for Python app dependencies to isolate them from ROS-managed packages.

```suggestion
RUN python3 -m venv /opt/venv && \
    /opt/venv/bin/pip install --no-cache-dir --upgrade pip && \
    /opt/venv/bin/pip install \
    pydantic==2.9.2 fastapi==0.115.0 uvicorn[standard]==0.30.6 pyyaml==6.0.2 slowapi==0.1.9
ENV PATH="/opt/venv/bin:$PATH"
```

---

#### 🟡 Mid — rosdep update in image build hurts availability and reproducibility

Running `rosdep update` during the Docker build introduces a live network dependency on external index state. Builds can fail intermittently or resolve different dependency metadata over time, making CI and production image creation unreliable. For robotics deployments, this undermines reproducibility and operational stability.

**Suggestion:** Avoid refreshing rosdep metadata during the image build unless strictly necessary. Use the preloaded rosdep database from the base image or perform the update in a controlled base-image pipeline.

```suggestion
RUN bash -c ". /opt/ros/jazzy/setup.bash && rosdep install --from-paths src --ignore-src -y"
```

---


### 📄 `README.md`

#### 🟠 High — Launch commands reference removed package/node

The README states that map management is handled by an external `map_management` package and the overview says only two nodes exist, but the launch instructions still tell users to run `map_control.launch.py` from `robot_gateway`. This is a functional documentation error that will cause deployment failures and operator confusion during setup.

**Suggestion:** Remove the stale launch command from this package, or replace it with the correct external package launch command if one exists.

```suggestion
ros2 launch map_management map_control.launch.py
```

---

#### 🔴 Critical — README advertises WebSocket as read-only but documents Joy publish

The WebSocket section explicitly says `Read-only subscription model` and `no ROS publishing from WS`, but the topics table still documents `/joy` as a publish topic for `ws_bridge`. This contradiction is operationally dangerous in a robot gateway because it misleads integrators about whether remote clients can inject motion/control input.

**Suggestion:** Remove the `/joy` topic entry unless inbound control is actually supported. Documentation must match the stated read-only safety model.

```suggestion

```

---

#### 🟠 High — Unsafe default bind address lacks security warning

The configuration documents `HOST_IP=0.0.0.0` as the default bind address for HTTP/WebSocket services but provides no warning that this exposes robot control interfaces on all network interfaces. For a gateway controlling physical hardware, publicly reachable defaults without an explicit security note materially increase attack surface, especially since the README does not document TLS or authentication requirements.

**Suggestion:** Document a loopback-safe default for local development and explicitly warn that `0.0.0.0` should only be used behind trusted networking, authentication, and TLS termination.

```suggestion
| `HOST_IP`         | `127.0.0.1` | Server bind address; use `0.0.0.0` only on trusted networks behind authentication/TLS |
```

---

#### 🟠 High — Delete service is documented with wrong interface type

The services table maps `map_management/map/delete` to `GetMap`, which is semantically incorrect and likely wrong for client integration. This is not cosmetic: consumers generating clients or wiring service calls from the README will invoke the wrong RPC contract and fail at runtime.

**Suggestion:** Replace the service type with the actual delete interface name used by `map_management_interfaces`. If the delete service is not yet finalized, avoid documenting an incorrect type.

```suggestion
| `map_management/map/delete`        | DeleteMap                     |
```

---


### 📄 `bridge_interface/common/config.py`


### 📄 `bridge_interface/common/schemas/api_schemas.py`


### 📄 `bridge_interface/common/schemas/robot.py`


### 📄 `bridge_interface/http_bridge/adapter.py`


### 📄 `bridge_interface/http_bridge/http_server.py`


### 📄 `bridge_interface/http_bridge/main.py`


### 📄 `bridge_interface/http_bridge/node.py`


### 📄 `bridge_interface/http_bridge/routers/map.py`


### 📄 `bridge_interface/http_bridge/routers/navigation.py`


### 📄 `bridge_interface/http_bridge/routers/status.py`


### 📄 `bridge_interface/launch/map_control.launch.py`


### 📄 `bridge_interface/map_control/node.py`


### 📄 `bridge_interface/setup.cfg`


### 📄 `bridge_interface_interfaces/srv/ChangeMap.srv`


### 📄 `bridge_interface_interfaces/srv/EditMap.srv`


### 📄 `bridge_interface_interfaces/srv/GetMap.srv`


### 📄 `bridge_interface_interfaces/srv/GetMapList.srv`


### 📄 `bridge_interface_interfaces/srv/SaveMap.srv`


### 📄 `docker-compose.yml`

#### 🟠 High — Host networking with published ports is unsafe

Both bridge services expose network listeners on 0.0.0.0 while also using host networking. In Docker Compose, published ports are ignored when network_mode: host is enabled, so these mappings provide no isolation or access control and can mislead operators into thinking exposure is constrained to declared ports. For a robot gateway, this increases the risk of unintended remote access to command interfaces and weakens deployment predictability.

**Suggestion:** Remove host networking for externally exposed bridge services and attach them to an explicit bridge network so only the declared ports are reachable. If ROS discovery truly requires host mode, then remove the ports section and bind HOST_IP to a restricted interface instead.

```suggestion
    ports:
      - "8000:8000"
    networks:
      - ros2_net
```

---

#### 🟠 High — WebSocket bridge repeats insecure host networking

The WebSocket bridge has the same unsafe and misleading configuration as the HTTP bridge: host networking plus a published port. This bypasses container-level network isolation for a remotely reachable control surface and makes the declared port mapping ineffective. For control-plane services in robotics, minimizing network exposure is a must-fix safety and security requirement.

**Suggestion:** Place the WebSocket bridge on an explicit Docker network and keep only the required published port. This preserves deterministic exposure and avoids giving the container full access to the host network stack.

```suggestion
    ports:
      - "9090:9090"
    networks:
      - ros2_net
```

---

#### 🟡 Mid — Declared network is commented out

After moving services toward an explicit network, the only network definition remains commented out. If the bridge services are switched off host networking, Compose will fail or silently fall back to defaults depending on how the file is used. This creates deployment inconsistency and can break ROS/service connectivity in production.

**Suggestion:** Enable the shared network definition so service networking is explicit and reproducible. If an external network is required by the environment, keep external: true; otherwise define a managed bridge network here.

```suggestion
networks:
  ros2_net:
    external: true
```

---

#### 🟡 Mid — Map path hardcodes environment-specific file

The map_server command now hardcodes /ws/maps/house/house.yaml. This couples startup to a specific directory layout in a sibling repository mount and will cause immediate container failure if that path is absent or renamed. For a robotics stack, brittle startup behavior degrades reliability and can block navigation services at runtime.

**Suggestion:** Parameterize the map file path through an environment variable so deployments can select a valid map without editing the compose file. This also keeps the command reusable across environments.

```suggestion
    command: sh -c 'ros2 run nav2_map_server map_server --ros-args -p yaml_filename:=${MAP_FILE:-/ws/maps/house/house.yaml}'
```

---


### 📄 `maps/TestHouse.yaml`


### 📄 `maps/house.yaml`


### 📄 `robot_gateway/common/exceptions.py`

#### 🟠 High — Base exception no longer carries HTTP status

Removing `status_code` from `BridgeInterfaceException` breaks the exception contract for any handler code that previously read `exc.status_code`. The new `ERROR_CODE_MAP` only works if every call site was updated to use type-based lookup, which is not shown in this diff. This creates a high-risk regression where errors can be emitted with incorrect default statuses or trigger attribute errors during HTTP response generation.

**Suggestion:** Preserve backward compatibility by keeping `status_code` on the base exception while still allowing centralized mapping. This avoids breaking existing handlers and keeps exception instances self-describing.

```suggestion
class BridgeInterfaceException(Exception):
    """Base exception for all bridge interface errors."""

    def __init__(self, message: str, status_code: int = 500):
```

---

#### 🟠 High — Service failures downgraded from 503 to 500

`ServiceCallException` previously encoded service unavailability semantics with HTTP 503. Mapping it to 500 changes client-visible behavior and can break retry logic, health monitoring, and upstream orchestration that distinguishes transient backend outages from internal server faults. For a robot gateway, misclassifying transient ROS/service transport failures reduces reliability and makes safe recovery harder.

**Suggestion:** Restore 503 for service-call failures so callers can safely classify transient downstream unavailability and apply retries/backoff appropriately.

```suggestion
    ServiceCallException: 503,
```

---

#### 🟠 High — Map operation failures incorrectly mapped to client error

`GetMapException` is now mapped to 400, but its message format (`Failed to get map data ...: {original_error}`) represents an internal operation failure, not invalid client input. Returning 400 for backend/storage/ROS retrieval failures misattributes server faults to the caller, suppresses alerting on real service defects, and can prevent proper retry/error handling upstream.

**Suggestion:** Map retrieval operation failures to 500 unless there is a separate, explicit validation exception for malformed client requests.

```suggestion
    GetMapException: 500,
```

---


### 📄 `robot_gateway/common/network.py`


### 📄 `robot_gateway/common/ros.py`

#### 🟠 High — LaserScan intensities omitted from serialization

The new LaserScan conversion drops `intensities`, which is part of the ROS message payload and is commonly required by downstream consumers for obstacle classification, filtering, and diagnostics. This is a functional regression because callers receiving the serialized scan cannot reconstruct the original message semantics. Since this file is a gateway serializer, it should preserve all externally relevant sensor fields unless the schema explicitly forbids them.

**Suggestion:** Include `scan_time` and `intensities` when constructing the serialized Scan model so the gateway does not silently discard sensor data. If the current schema lacks these fields, extend the schema before merging this change.

```suggestion
    return Scan(
        angle_min=msg.angle_min,
        angle_max=msg.angle_max,
        angle_increment=msg.angle_increment,
        time_increment=msg.time_increment,
        scan_time=msg.scan_time,
        range_min=msg.range_min,
        range_max=msg.range_max,
        ranges=list(msg.ranges),
        intensities=list(msg.intensities),
    ).model_dump()
```

---

#### 🟠 High — Occupancy grid origin is serialized incompletely

The new map serializer only exports `origin.position.x`, `origin.position.y`, and `orientation.w`. ROS `OccupancyGrid.info.origin` is a full 3D pose. Dropping `position.z` and quaternion `x/y/z` makes the serialized map pose invalid for any non-trivial rotation and prevents correct frame reconstruction by consumers. This is a data corruption issue in the gateway boundary.

**Suggestion:** Serialize the complete origin pose, including all position and quaternion components. If the imported schema models currently do not support these fields, they must be extended; otherwise the gateway will emit lossy map metadata.

```suggestion
                position=Position(
                    x=msg.info.origin.position.x,
                    y=msg.info.origin.position.y,
                    z=msg.info.origin.position.z,
                ),
                orientation=Orientation(
                    x=msg.info.origin.orientation.x,
                    y=msg.info.origin.orientation.y,
                    z=msg.info.origin.orientation.z,
                    w=msg.info.origin.orientation.w,
                ),
```

---

#### 🟡 Mid — Ranges are passed as ROS sequences without normalization

`msg.ranges` is forwarded directly from the ROS message object. ROS message sequences are not guaranteed to be plain Python lists, and downstream JSON serialization/model validation may fail or behave inconsistently depending on transport and schema expectations. For a gateway boundary, message arrays should be normalized to built-in Python containers before dumping.

**Suggestion:** Materialize the ROS sequence into a plain list before building the model. Apply the same treatment to any other array fields such as `intensities` when added.

```suggestion
        ranges=list(msg.ranges),
```

---


### 📄 `robot_gateway/common/schemas/api_schemas.py`

#### 🟠 High — Update models overwrite fields unintentionally

`UpdatePoseModel` and `UpdateRouteModel` use concrete defaults (`0.0`, `""`, `[]`) for fields that are semantically optional in a partial update. This makes it impossible to distinguish 'field omitted by client' from 'client explicitly wants empty/zero', which can silently reset persisted pose/route data during PATCH-style updates. In a robot gateway, unintended waypoint or route mutation is a reliability and operational safety issue.

**Suggestion:** Make update fields nullable so omitted values remain `None` and downstream code can apply only the provided fields.

```suggestion
class UpdatePoseModel(BaseModel):
    """Request model for updating an existing pose."""

    name: Optional[str] = Field(default=None, description="New name.")
    x: Optional[float] = Field(default=None, description="New position x.")
    y: Optional[float] = Field(default=None, description="New position y.")
    yaw: Optional[float] = Field(default=None, description="New yaw angle.")
    notes: Optional[str] = Field(default=None, description="New notes.")
```

---

#### 🟠 High — Route update cannot distinguish omitted items

`UpdateRouteModel.items` defaults to an empty list, so a client that omits `items` will be interpreted as requesting full route clearing. That is a destructive ambiguity for optimistic-lock updates and can erase navigation routes unexpectedly. Partial update schemas must preserve omission semantics.

**Suggestion:** Make mutable update fields optional and default to `None`, so handlers can detect whether the client actually requested a route rename or waypoint replacement.

```suggestion
class UpdateRouteModel(BaseModel):
    """Request model for updating an existing route."""

    base_version: int = Field(..., description="Expected current version (optimistic lock).")
    name: Optional[str] = Field(default=None, description="New route name.")
    items: Optional[list[RouteItemModel]] = Field(default=None, description="New ordered waypoint list.")
```

---

#### 🟠 High — Movement schema lacks finite-value validation

`MoveCommand` constrains numeric ranges but still accepts non-finite floats such as `NaN` and `Infinity` unless explicitly rejected. Pydantic float fields do not guarantee finite values by range checks alone in all cases, and downstream robot-control code receiving non-finite coordinates/orientations can propagate invalid transforms or crash motion planners. External command payloads must reject non-finite numbers strictly.

**Suggestion:** Use strict finite float validation for motion inputs. At minimum, reject `NaN`/`Infinity` via Pydantic field constraints on every motion component.

```suggestion
class MoveCommand(BaseModel):
    """Command to move robot to specified position."""

    pos_x: float = Field(
        ...,
        description="Position X",
        ge=-99.0,
        le=99.0,
        allow_inf_nan=False,
    )
```

---

#### 🟡 Mid — API timestamps use fixed Bangkok timezone

The response schema emits timestamps in a hard-coded UTC+7 timezone. In distributed gateways, fixed local offsets are unsafe for correlation across robot controllers, fleet backends, logs, and watchdog events, and they increase the chance of ordering mistakes during incident analysis. API timestamps should be standardized to UTC and let clients localize if needed.

**Suggestion:** Generate timezone-aware UTC timestamps to provide a stable, system-wide canonical time reference.

```suggestion
def get_current_time():
    """Get current time in UTC."""
    return datetime.now(timezone.utc)
```

---


### 📄 `robot_gateway/common/schemas/robot.py`

#### 🟠 High — Battery current cannot represent discharge

The schema enforces `amp >= 0`, which rejects negative current values. On robotic platforms, battery discharge is commonly represented as negative current; this validation will either fail on legitimate telemetry or force upstream producers to distort the sign. That breaks monitoring logic and can hide power-related faults.

**Suggestion:** Allow signed current values while keeping the field typed as float.

```suggestion
    amp: float = 0.0
```

---

#### 🟡 Mid — Battery state-of-charge lacks upper bound

The schema only constrains `soc` to be non-negative, so values above 100 are accepted. State-of-charge is a bounded percentage-like field in most robot telemetry pipelines; allowing impossible values degrades safety checks, alerting, and fleet-side battery management decisions.

**Suggestion:** Constrain state-of-charge to a valid 0-100 range.

```suggestion
    soc: float = Field(0.0, ge=0.0, le=100.0)
```

---

#### 🟠 High — Timestamp nanoseconds accepts invalid range

ROS2 timestamps require nanoseconds to be within [0, 999,999,999]. Without validation, malformed timestamps can be accepted and propagated into downstream consumers, causing incorrect ordering, serialization failures, or ROS interoperability bugs.

**Suggestion:** Add a range constraint matching ROS2 timestamp semantics.

```suggestion
    nanosec: int = Field(ge=0, le=999_999_999)
```

---

#### 🟠 High — Unbounded map payload enables memory abuse

The occupancy grid `data` field accepts an arbitrary-length string with no validation. For an externally supplied schema, this permits oversized payloads that can trigger excessive memory allocation, slow parsing, or DoS conditions. The field should be bounded and ideally tied to `width * height` expectations for encoded map content.

**Suggestion:** At minimum, cap the payload length to reduce abuse potential. If feasible later, add a model-level validator to enforce consistency with map dimensions and expected encoding.

```suggestion
    data: str = Field(max_length=16_777_216)
```

---


### 📄 `robot_gateway/common/utils.py`


### 📄 `robot_gateway/config/params.yaml`

#### 🔴 Critical — Wildcard CORS enables any origin access

Both bridges allow requests from any web origin via `allow_origin: ["*"]`. For a robot control gateway, this is a serious security risk: any malicious site opened in an operator's browser can issue cross-origin requests or establish browser-based control channels to the exposed service. Given the gateway binds to all interfaces, this materially increases the attack surface and can lead to unauthorized robot commands.

**Suggestion:** Restrict allowed origins to explicitly trusted operator or fleet-management domains. If multiple environments are needed, list them individually rather than using a wildcard.

```suggestion
    allow_origin: ["https://fleet.example.com"]
```

---

#### 🟠 High — HTTP bridge listens on all network interfaces

Binding the HTTP bridge to `0.0.0.0` exposes the service on every reachable interface, including unintended LAN or WAN paths. For a robot gateway, unnecessary exposure of the command/control API materially increases the risk of unauthorized access and remote misuse, especially when paired with permissive CORS.

**Suggestion:** Bind to localhost by default unless deployment explicitly requires remote access through a secured reverse proxy, VPN, or firewall-controlled interface.

```suggestion
    host_ip: "127.0.0.1"
```

---

#### 🟠 High — WebSocket bridge exposed on all interfaces

The WebSocket bridge is also bound to `0.0.0.0`, making a low-latency control channel reachable from any network path to the host. WebSockets are commonly used for streaming commands and telemetry; exposing them broadly without evidence of transport security or authentication is a major security and safety concern for robot operation.

**Suggestion:** Restrict the WebSocket listener to localhost by default and place any required external exposure behind authenticated, TLS-terminating infrastructure.

```suggestion
    host_ip: "127.0.0.1"
```

---


### 📄 `robot_gateway/http_bridge/adapter.py`

#### 🟠 High — Import will fail if adapters package is absent

This module hard-depends on symbols from `http_bridge.adapters`, but the provided Dependency Context for `http_bridge/adapters.py` is empty. As written, importing `robot_gateway.http_bridge.adapter` will raise `ImportError` at module import time if the target package/module does not actually export these names, breaking backward compatibility instead of preserving it.

**Suggestion:** Guard the compatibility import and raise a clear compatibility error only when the re-export target is unavailable. This avoids opaque startup failures and makes the compatibility shim safer to deploy across mixed versions.

```suggestion
try:
    from http_bridge.adapters import (
        BaseAdapter,
        NavigationAdapter,
        StatusAdapter,
        MapAdapter,
        SlamAdapter,
        PoseAdapter,
        RouteAdapter,
    )
except ImportError as exc:
    raise ImportError(
        "robot_gateway.http_bridge.adapter requires http_bridge.adapters to export the adapter classes"
    ) from exc
```

---


### 📄 `robot_gateway/http_bridge/adapters/__init__.py`


### 📄 `robot_gateway/http_bridge/adapters/base_adapter.py`

#### 🟡 Mid — Missing runtime type validation for node

The constructor accepts any object and stores it as `self.node` without validation. In a gateway adapter layer, this creates a failure mode where an invalid dependency is injected and only fails later at command execution time, making faults harder to detect and potentially destabilizing robot command handling paths. Since `HttpBridgeNode` is the required dependency in the type hint, this should be enforced at construction time.

**Suggestion:** Validate that `node` is an instance of `HttpBridgeNode` and fail fast with a clear exception before storing it.

```suggestion
    def __init__(self, node: HttpBridgeNode):
        if not isinstance(node, HttpBridgeNode):
            raise TypeError("node must be an instance of HttpBridgeNode")
        self.node = node
```

---

#### 🟡 Mid — Abstract base class defines no required interface

`BaseAdapter` inherits from `ABC` but does not declare any abstract methods or properties. This means subclasses are not forced to implement a minimum adapter contract, so incompatible adapters can be instantiated and wired into the bridge without required behavior. In an adapter layer bridging external HTTP traffic to robot control, lack of enforced interface consistency increases integration-time failures and unsafe runtime behavior.

**Suggestion:** Define at least one abstract member representing the required adapter contract so subclasses cannot be instantiated without implementing expected behavior.

```suggestion
class BaseAdapter(ABC):
    """Base adapter providing shared ROS node access."""

    @property
    def node(self) -> HttpBridgeNode:
        return self._node
```

---

#### 🟡 Mid — Node reference is publicly mutable

Storing the dependency as a public attribute allows arbitrary reassignment after construction. In a concurrent gateway service, replacing the ROS/bridge node reference at runtime can lead to inconsistent state, race-prone behavior, or commands being routed through the wrong node instance. This is especially risky in robot control paths where stable ownership of the communication node matters for reliability.

**Suggestion:** Store the dependency in a private attribute and expose it through a read-only property to prevent accidental mutation after initialization.

```suggestion
        self._node = node
```

---


### 📄 `robot_gateway/http_bridge/adapters/dependencies.py`

#### 🟠 High — Unsafe unchecked app.state adapter access

Each dependency directly reads a dynamic attribute from `request.app.state` without any validation. If startup wiring is incomplete, misordered, or a test app omits one adapter, FastAPI will raise `AttributeError` and return a generic 500. In a robot gateway, this turns a configuration/runtime wiring fault into an unstructured server failure instead of a controlled service-unavailable response, reducing reliability and diagnosability.

**Suggestion:** Validate the state attribute before returning it and fail with an explicit HTTP error when the adapter is not initialized. Apply the same pattern to every dependency getter in this file.

```suggestion
def get_navigation_adapter(request: Request) -> NavigationAdapter:
    adapter = getattr(request.app.state, "navigation_adapter", None)
    if adapter is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail="Navigation adapter not initialized")
    return adapter
```

---

#### 🟡 Mid — No runtime type validation for injected adapters

The return annotations are not enforced at runtime. Because `app.state` is an untyped dynamic container, a wrong object can be assigned during startup and still be returned here silently. That can surface later as invalid command routing or method failures deep in request handling, which is especially risky for robot control paths where the wrong backend instance may bypass expected safety behavior.

**Suggestion:** Check that the retrieved object is an instance of the expected adapter class before returning it, and raise a controlled server error if the wiring is invalid. Mirror this check across all adapter dependency functions.

```suggestion
def get_status_adapter(request: Request) -> StatusAdapter:
    adapter = getattr(request.app.state, "status_adapter", None)
    if adapter is None or not isinstance(adapter, StatusAdapter):
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail="Status adapter misconfigured")
    return adapter
```

---


### 📄 `robot_gateway/http_bridge/adapters/map_adapter.py`

#### 🔴 Critical — Unsafe decompression can exhaust memory

The adapter decompresses `response.pgm_data` without any size or ratio guard. Because this path handles external/service-provided payloads, a malformed or highly compressed map can trigger unbounded allocation during `utils.decompress(...)`, causing process memory exhaustion or gateway instability. In a robot gateway, this is a reliability and safety issue because map retrieval can stall or crash the bridge. Catching `zlib.error` is not sufficient; successful decompression of a zip bomb still harms the process.

**Suggestion:** Validate the compressed payload size before decompression and enforce a maximum decompressed size after decompression. Reject oversized payloads with `MapDecompressionException` before constructing `MapData`.

```suggestion
                if len(response.pgm_data) > 10 * 1024 * 1024:
                    raise MapDecompressionException(map_name, "Compressed map payload exceeds 10 MiB limit")
                decompressed_data = utils.decompress(response.pgm_data)
                if len(decompressed_data) > 100 * 1024 * 1024:
                    raise MapDecompressionException(map_name, "Decompressed map payload exceeds 100 MiB limit")
                return MapData.from_raw_data(
```

---

#### 🟠 High — Update request fields mismatch get/load contract

The adapter reads custom map metadata from `response.editor_custom_data` and `response.robot_custom_data`, but writes to `request.robot_custom_point` and `request.editor_custom_point`. This inconsistency strongly suggests the wrong request fields are being populated. If the service request actually expects `*_custom_data`, the current code silently drops metadata updates. If the service truly uses `*_point`, the naming mismatch across operations still indicates an incompatible contract that will corrupt or omit map metadata.

**Suggestion:** Populate request fields that match the read-side contract and service schema for custom metadata. Use the `*_custom_data` fields unless the generated service definition explicitly requires a different name.

```suggestion
        request.robot_custom_data = map_cmd.robot_custom
        request.editor_custom_data = map_cmd.editor_custom
```

---

#### 🟠 High — Delete uses wrong service request type

The delete path constructs `GetMap.Request()` and passes it to `call_delete_map`. Reusing a request type from a different service is a correctness bug unless `call_delete_map` is explicitly implemented to accept `GetMap.Request`, which would be an API smell. In ROS service clients, request types must match the target service exactly; otherwise this fails at runtime or sends an invalid payload.

**Suggestion:** Use the request type generated for the delete-map service import and send that to `call_delete_map`. If no delete service exists, this adapter method should not be implemented with a mismatched request type.

```suggestion
        request = DeleteMap.Request()
        request.map_name = map_name
        await self.node.call_delete_map(request)
```

---

#### 🟡 Mid — Save return type likely wrong

`save()` is annotated to return `str`, but unlike `load()` it directly returns the result of `await self.node.call_save_map(request)`. Service client calls typically return a response object, not a raw string. Returning the full response object while advertising `str` will break callers and bypass schema normalization in the adapter layer.

**Suggestion:** Extract and return the concrete response field intended by the adapter contract, or update the method signature if the full response object is desired. Keep the adapter API stable and typed.

```suggestion
        response = await self.node.call_save_map(request)
        return response.editor_custom_data
```

---


### 📄 `robot_gateway/http_bridge/adapters/navigation_adapter.py`

#### 🔴 Critical — Stop command can issue non-zero velocity

The stop path forwards caller-provided velocity values directly into TwistStamped. In a robot gateway, a stop operation must be fail-safe and deterministic. Allowing external payloads to define stop velocities can cause continued motion or unexpected actuation if the client sends stale, malformed, or malicious values. This is a safety-critical issue because the method name and contract imply an immediate halt, but the implementation can command movement instead.

**Suggestion:** Override all linear velocity components to zero in stop(), regardless of the incoming CmdVel payload. A true stop command should not depend on external input.

```suggestion
        twist.twist.linear.x = 0.0
        twist.twist.linear.y = 0.0
        twist.twist.linear.z = 0.0
```

---

#### 🔴 Critical — Angular stop path trusts external payload

The stop implementation also propagates angular components from CmdVel. This means stop() may command rotation instead of halting. For mobile robots and manipulators, residual angular velocity is a serious safety hazard and can defeat watchdog or operator expectations around emergency stop semantics.

**Suggestion:** Force all angular velocity components to zero in stop(). If non-zero braking behavior is ever required, it should be a separate, explicitly named API with its own validation and safety constraints.

```suggestion
        twist.twist.angular.x = 0.0
        twist.twist.angular.y = 0.0
        twist.twist.angular.z = 0.0
```

---

#### 🟠 High — Goal pose is published without input validation

start() copies all pose fields from MoveCommand directly into a PoseStamped and publishes them immediately. There is no validation that coordinates are finite or that the quaternion is valid. Unchecked NaN/Inf values or a zero/non-normalized quaternion can break downstream ROS consumers, trigger navigation failures, or produce undefined robot behavior. In a gateway receiving external payloads, strict input validation is required before publishing to robot control topics.

**Suggestion:** Validate all numeric fields before publishing. At minimum, reject non-finite position/orientation values and ensure the quaternion norm is non-zero and approximately normalized.

```suggestion
        import math
        values = [
            nav_command.pos_x, nav_command.pos_y, nav_command.pos_z,
            nav_command.ori_x, nav_command.ori_y, nav_command.ori_z, nav_command.ori_w,
        ]
        if not all(math.isfinite(v) for v in values):
            raise ValueError("Navigation command contains non-finite values")
        norm = math.sqrt(
            nav_command.ori_x ** 2 + nav_command.ori_y ** 2 + nav_command.ori_z ** 2 + nav_command.ori_w ** 2
        )
        if norm == 0.0 or not math.isclose(norm, 1.0, rel_tol=1e-3, abs_tol=1e-3):
            raise ValueError("Navigation command contains invalid quaternion")
        self.node.publish_navigation(pose)
```

---

#### 🟡 Mid — Asynchronous API performs blocking publish calls

Both methods are declared async but execute synchronous ROS publish operations directly. If publish_navigation() or publish_cmd_vel() blocks on middleware backpressure, serialization, or executor state, this will stall the event loop handling external HTTP/WebSocket traffic. In a real-time gateway, blocking inside async handlers degrades responsiveness and can delay watchdog-driven stop commands.

**Suggestion:** Offload the publish call to a worker thread so the async interface remains non-blocking. Apply the same pattern to publish_cmd_vel().

```suggestion
        import asyncio
        await asyncio.to_thread(self.node.publish_navigation, pose)
```

---


### 📄 `robot_gateway/http_bridge/adapters/pose_adapter.py`

#### 🟠 High — Create request drops pose tags

The create adapter does not forward any tags from the API model into the ROS service request. This causes silent data loss for clients that submit tagged poses and makes create behavior inconsistent with capture_current, which does pass tags through. In a waypoint management gateway, silently discarding metadata is a functional bug because downstream filtering and retrieval can no longer rely on stored tags.

**Suggestion:** Propagate tags from the incoming model when present before invoking the service. Use a safe fallback to avoid attribute errors if the schema omits the field.

```suggestion
        request.notes = pose_request.note
        request.tags = getattr(pose_request, "tags", [])
        response = await self.node.call_create_pose(request)
```

---

#### 🟠 High — Update request cannot change frame or map

The update adapter only forwards name and planar pose fields, but omits map_id and frame_id. If the UpdatePose service supports these fields, the gateway prevents clients from correcting a pose's reference frame or map assignment, producing partial updates and inconsistent state. This is especially risky in robotics because stale frame/map metadata can lead to commands being interpreted in the wrong coordinate system.

**Suggestion:** Forward frame and map identifiers as part of the update request, using defensive getattr access if the schema allows partial updates.

```suggestion
        request.name = update_request.name
        request.map_id = getattr(update_request, "map_id", "")
        request.frame_id = getattr(update_request, "frame_id", "")
        request.x = update_request.x
        request.y = update_request.y
        request.yaw = update_request.yaw
```

---

#### 🟡 Mid — List endpoint lacks defensive pagination bounds

The adapter forwards offset and limit directly to the backend service without enforcing any bounds. Negative offsets or excessively large limits can trigger invalid service requests, unnecessary memory use, or latency spikes if the backing service attempts to materialize huge pose lists. Gateway adapters should enforce sane limits at the boundary to protect service reliability.

**Suggestion:** Clamp offset to zero and limit to a small maximum before issuing the service call. This prevents abusive or accidental unbounded queries from propagating into the ROS layer.

```suggestion
        request.offset = max(0, offset)
        request.limit = min(max(1, limit), 100)
```

---

#### 🟠 High — Create note field likely mapped from wrong schema attribute

The create method reads pose_request.note, while the rest of this adapter and response model consistently use notes. This asymmetry strongly suggests a schema mismatch that can raise an AttributeError at runtime or silently ignore the provided notes field depending on the actual model definition. Given the empty Dependency Context for api_schemas, this should be treated as a high-risk integration bug.

**Suggestion:** Use the plural field name consistently, or fall back safely if both variants may exist during schema transition.

```suggestion
        request.notes = getattr(pose_request, "notes", getattr(pose_request, "note", ""))
```

---


### 📄 `robot_gateway/http_bridge/adapters/route_adapter.py`

#### 🟠 High — Unbounded list query can overload route service

The adapter forwards client-controlled pagination values directly to the backend without any local validation. A negative offset/limit or an excessively large limit can trigger invalid ROS service requests, excessive memory usage, or long-running route enumerations that degrade gateway responsiveness. In a robot gateway, unbounded external queries are a reliability and availability risk because they can starve command-processing paths.

**Suggestion:** Clamp offset to a non-negative value and enforce a strict upper bound for limit before issuing the service call. Reject invalid values early or normalize them to safe bounds to prevent backend abuse.

```suggestion
        request.offset = max(0, offset)
        request.limit = max(1, min(limit, 100))
```

---

#### 🔴 Critical — Route item payloads are passed without structural validation

Both create() and update() blindly translate externally supplied route items into ROS messages. There is no validation that sequence_index is ordered/unique, pose_id is present, or stop_duration_sec is non-negative. This can result in malformed routes being accepted and later executed unpredictably by downstream motion components, which is a direct safety and reliability concern for robotic navigation flows.

**Suggestion:** Validate the route items before building ROS messages. At minimum, reject empty pose_id values, negative stop durations, and duplicate or non-monotonic sequence indexes. Perform the same validation in update().

```suggestion
        if any(not item.pose_id or item.stop_duration_sec < 0 for item in route_request.items):
            raise ValueError("Each route item must include a pose_id and non-negative stop_duration_sec")
        if len({item.sequence_index for item in route_request.items}) != len(route_request.items):
            raise ValueError("Route item sequence_index values must be unique")
        request.items = [_build_route_item(item) for item in route_request.items]
```

---

#### 🔴 Critical — Update path accepts malformed route items

The update() path has the same missing input validation as create(), but is more dangerous because it can corrupt existing persisted routes. A malformed update payload can overwrite a known-good route definition with invalid sequence data or negative dwell times, causing operational regressions without any gateway-side guardrail.

**Suggestion:** Apply the same strict validation in update() before constructing the ROS request. Reject invalid item payloads instead of delegating validation to downstream services.

```suggestion
        if any(not item.pose_id or item.stop_duration_sec < 0 for item in update_request.items):
            raise ValueError("Each route item must include a pose_id and non-negative stop_duration_sec")
        if len({item.sequence_index for item in update_request.items}) != len(update_request.items):
            raise ValueError("Route item sequence_index values must be unique")
        request.items = [_build_route_item(item) for item in update_request.items]
```

---


### 📄 `robot_gateway/http_bridge/adapters/slam_adapter.py`

#### 🟠 High — Wrong request field breaks SLAM trigger

`check_status()` populates `SlamModel` using `is_slam_node_active` and `is_slam_running`, but `trigger()` reads `slam_request.active`, which is not shown anywhere in this diff and is inconsistent with the only visible `SlamModel` fields. If `SlamModel` does not define `active`, this raises at runtime and the HTTP bridge cannot trigger SLAM. Even if it does exist, the adapter is mixing two different state representations, which is error-prone at the API boundary.

**Suggestion:** Use the same field naming convention that the adapter exposes in `check_status()`, so the trigger request is built from a defined SLAM activation field rather than an inconsistent attribute.

```suggestion
request.data = slam_request.is_slam_running
```

---

#### 🟠 High — Service response success is ignored

`trigger()` returns the raw result of `self.node.trigger_slam(request)` while the method signature promises `bool`. For ROS `std_srvs/SetBool`, the service response is typically an object carrying `success` and `message`, not a boolean. Returning the response object violates the declared contract and can cause incorrect truthiness handling by callers, masking failed SLAM start/stop requests.

**Suggestion:** Await the service call, then return its explicit success flag so the adapter contract remains boolean and failures are not silently misinterpreted.

```suggestion
response = await self.node.trigger_slam(request)
        return response.success
```

---


### 📄 `robot_gateway/http_bridge/adapters/status_adapter.py`

#### 🔴 Critical — Returns fabricated battery status

`get_battery()` currently constructs and returns a default `Battery()` without querying any robot state. That makes every caller receive synthetic data, which is a correctness and safety issue for a robot gateway because upstream systems may make decisions based on an invalid charge level. The dependency context does not show any `Battery` defaults or validation contract, so returning an empty instance is especially risky.

**Suggestion:** Fetch battery telemetry from the underlying robot/client exposed by `BaseAdapter`, validate that data is present, and build the `Battery` schema from real values. If telemetry is unavailable, raise a controlled exception instead of fabricating status.

```suggestion
        battery_status = await self.robot_client.get_battery()
        if battery_status is None:
            raise RuntimeError("Battery status unavailable")
        return Battery(**battery_status)
```

---

#### 🟠 High — No guard for adapter dependency availability

This method assumes the adapter has access to a live backend but performs no readiness check before serving status. In a gateway service, querying status while disconnected or uninitialized should fail fast with an explicit error; otherwise later attribute access or transport errors become nondeterministic and harder to handle safely.

**Suggestion:** Add an explicit readiness check against the backend/client managed by `BaseAdapter` before performing the request, and fail with a clear exception when the adapter is not connected.

```suggestion
    async def get_battery(self) -> Battery:
        """Get current battery status."""
        if getattr(self, "robot_client", None) is None:
            raise RuntimeError("Robot client is not initialized")

        battery_status = await self.robot_client.get_battery()
        if battery_status is None:
            raise RuntimeError("Battery status unavailable")
        return Battery(**battery_status)
```

---


### 📄 `robot_gateway/http_bridge/http_server.py`

#### 🟠 High — Unsafe adapter lookup can crash startup

The app initialization dereferences required adapters with direct dictionary indexing. If any adapter is missing or misspelled in the caller-provided `adapters` map, startup raises `KeyError` with no controlled error path. For a robot gateway, failing with an opaque exception during boot is a reliability issue and makes misconfiguration hard to diagnose in production.

**Suggestion:** Validate the required adapter set explicitly and fail fast with a descriptive exception before mutating app state. This prevents partial initialization and provides deterministic configuration validation.

```suggestion
    required_adapters = {
        "navigation_adapter",
        "status_adapter",
        "map_adapter",
        "slam_adapter",
        "pose_adapter",
        "route_adapter",
    }
    missing_adapters = required_adapters - set(adapters)
    if missing_adapters:
        raise ValueError(
            f"Missing required adapters: {', '.join(sorted(missing_adapters))}"
        )

    app.state.navigation_adapter = adapters["navigation_adapter"]
    app.state.status_adapter = adapters["status_adapter"]
    app.state.map_adapter = adapters["map_adapter"]
```

---

#### 🟠 High — CORS configuration lacks origin validation

`allow_origin` is passed directly into `CORSMiddleware` without any validation. If the caller supplies `['*']` or an empty/invalid list, the HTTP bridge can unintentionally expose robot-control endpoints cross-origin to arbitrary browser contexts. Given this service controls robot operations, permissive or malformed CORS is a material security risk.

**Suggestion:** Reject empty or wildcard origins at startup and pass a validated list into CORS. This enforces explicit trusted origins instead of silently accepting insecure configuration.

```suggestion
    if not allow_origin or "*" in allow_origin:
        raise ValueError("allow_origin must contain explicit trusted origins only")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origin,
        allow_credentials=False,
        allow_methods=["POST", "GET", "PUT", "DELETE"],
        allow_headers=["*"],
    )
```

---

#### 🟡 Mid — Index route can crash on package lookup failure

`get_package_share_directory("robot_gateway")` can raise if the package is not installed or the environment is misconfigured. That exception is not handled, so a simple GET `/` can return an unstructured 500 and bypass the API's error schema. This is a reliability issue for health/status access and complicates operational diagnosis.

**Suggestion:** Wrap package resolution in a defensive try/except and return a structured error response when the share directory cannot be resolved. This keeps the endpoint predictable under deployment/configuration failures.

```suggestion
        try:
            file_path = os.path.join(
                get_package_share_directory("robot_gateway"), "statics", "index.html"
            )
        except Exception:
            return JSONResponse(
                status_code=500,
                content=ApiResponse(
                    action="error",
                    status="error",
                    message="robot_gateway share directory not found",
                ).model_dump(mode="json"),
            )
```

---

#### 🟡 Mid — Unhandled exceptions return inconsistent error payloads

Only `BridgeInterfaceException` and `RateLimitExceeded` are mapped. Any other exception from routers, adapter calls, or filesystem operations will fall through to FastAPI's default 500 response, which is inconsistent with the API contract and may leak internal details depending on runtime configuration. For a gateway interfacing with robot hardware, unexpected failures should be normalized to a safe, deterministic payload.

**Suggestion:** Add a final catch-all exception handler that returns a generic structured 500 response. This preserves API consistency and avoids exposing raw internal errors to clients.

```suggestion
    @app.exception_handler(BridgeInterfaceException)
    async def bridge_interface_exception_handler(
        request: Request, exc: BridgeInterfaceException
    ):
        """Handle custom BridgeInterfaceException and convert to HTTP response."""
        code = next(
            (code for cls, code in ERROR_CODE_MAP.items() if isinstance(exc, cls)),
            500,
        )
        return JSONResponse(
            status_code=code,
            content=ApiResponse(
                action=request.url.path,
                status="error",
                message=exc.message,
            ).model_dump(mode="json"),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        return JSONResponse(
            status_code=500,
            content=ApiResponse(
                action=request.url.path,
                status="error",
                message="Internal server error",
            ).model_dump(mode="json"),
        )
```

---


### 📄 `robot_gateway/http_bridge/limiter.py`

#### 🟠 High — IP-based keying breaks behind reverse proxies

Using `get_remote_address` directly makes rate limiting depend on the immediate client socket address. In common gateway deployments behind ingress, load balancers, or reverse proxies, this often resolves to the proxy IP, causing all clients to share one bucket or allowing incorrect attribution if proxy headers are later trusted inconsistently elsewhere. This is a reliability and abuse-prevention issue because valid operators can be throttled together and malicious traffic can hide behind shared infrastructure.

**Suggestion:** Use a key function that prefers a validated forwarded client IP when present and falls back to the socket address. Only trust forwarded headers from known proxy infrastructure in the surrounding app configuration.

```suggestion
def _rate_limit_key(request):
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return get_remote_address(request)


limiter = Limiter(key_func=_rate_limit_key)
```

---

#### 🟠 High — No default limiter policy allows unlimited requests

This module creates a shared limiter object but does not enforce any baseline policy. If a route is added without an explicit `@limiter.limit(...)` decorator, it will be completely unthrottled. For a robot gateway, missing rate limits on even one command or session endpoint is a safety and reliability hazard because burst traffic can starve control paths or flood downstream robot interfaces.

**Suggestion:** Set a conservative `default_limits` policy on the shared limiter so endpoints are protected even when developers forget to annotate a route. Individual routers can still override with stricter or looser limits where justified.

```suggestion
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["60/minute"],
)
```

---


### 📄 `robot_gateway/http_bridge/main.py`

#### 🟠 High — Executor is never explicitly stopped

The ROS executor is started on a daemon thread, but shutdown only destroys the node and calls rclpy.shutdown(). Without explicitly stopping the executor first, the spin thread can remain blocked or race against node destruction during teardown. In a robot gateway this is a reliability problem because background callbacks may still be executing while transport and node resources are being torn down, producing undefined shutdown behavior.

**Suggestion:** Shut down the executor before destroying the node, then join the ROS thread, and only then shut down rclpy. This gives the spin loop a deterministic exit path and avoids teardown races.

```suggestion
    finally:
        # Ensure cleanup happens even if uvicorn crashes
        executor.shutdown()
        ros_thread.join(timeout=5.0)
        http_bridge_node.destroy_node()
        rclpy.shutdown()
```

---

#### 🟠 High — No fail-safe handling if ROS thread dies

The HTTP server is started independently of the executor thread, but there is no monitoring for executor startup failure or unexpected thread termination. If executor.spin exits due to an exception, the REST API can continue accepting robot commands while ROS callbacks, publishers, or subscriptions are no longer processing. That creates a dangerous split-brain state for a control gateway.

**Suggestion:** Wrap executor.spin in a guarded function that logs failures and terminates the process, or at minimum verify the ROS thread remains alive before serving HTTP traffic. This prevents the gateway from exposing control endpoints when its ROS backend is unavailable.

```suggestion
    def _spin_executor():
        try:
            executor.spin()
        except Exception as exc:
            http_bridge_node.get_logger().fatal(f"ROS executor stopped unexpectedly: {exc}")
            raise

    ros_thread = threading.Thread(target=_spin_executor, daemon=True)
    ros_thread.start()
    if not ros_thread.is_alive():
        raise RuntimeError("Failed to start ROS executor thread")

    try:
        uvicorn.run(app, host=http_bridge_node.host_ip, port=http_bridge_node.host_port)
```

---

#### 🟠 High — HTTP server lacks explicit TLS enforcement

The gateway exposes robot control over HTTP using uvicorn.run with only host and port. There is no indication of TLS configuration or any transport security guard before serving. For an external control bridge, accepting plaintext traffic is a security risk because commands and status can be intercepted or modified in transit.

**Suggestion:** Require TLS configuration before startup, or fail closed when certificates are not configured. If TLS termination is delegated elsewhere, enforce a configuration check here so insecure direct deployment does not occur silently.

```suggestion
        if not getattr(http_bridge_node, "ssl_certfile", None) or not getattr(http_bridge_node, "ssl_keyfile", None):
            raise RuntimeError("TLS must be configured for the HTTP bridge")
        uvicorn.run(
            app,
            host=http_bridge_node.host_ip,
            port=http_bridge_node.host_port,
            ssl_certfile=http_bridge_node.ssl_certfile,
            ssl_keyfile=http_bridge_node.ssl_keyfile,
        )
```

---


### 📄 `robot_gateway/http_bridge/node.py`

#### 🔴 Critical — Delete-map client uses wrong service type

The delete-map client is created with GetMap instead of a dedicated delete service type. That is a hard correctness bug: request/response serialization will not match the server if the actual endpoint `map_management/map/delete` is not implemented with `GetMap`. The rest of the file already assumes delete semantics via `DeleteMapException`, so this mismatch can cause runtime failures or false success handling during a destructive operation.

**Suggestion:** Create the client with the delete service contract instead of reusing GetMap. Import the correct service type and use it consistently in both client creation and the delete call signature.

```suggestion
        self._delete_map_service_client = self.create_client(
            DeleteMap, "map_management/map/delete"
        )
```

---

#### 🟠 High — Delete-map request typed as GetMap

The delete API is declared as `GetMap.Request`, which is inconsistent with a delete operation and tightly couples request validation to the wrong contract. If the delete service contains any field differences, this method will fail at runtime. Even if the request currently happens to share `map_name`, this is still a brittle interface bug on a safety-relevant map-management path.

**Suggestion:** Use the correct delete request type so the method signature matches the actual ROS service contract and type checking catches misuse earlier.

```suggestion
    async def call_delete_map(self, delete_map_request: DeleteMap.Request) -> None:
```

---

#### 🔴 Critical — Velocity publish path lacks any safety gating

This node exposes a direct `cmd_vel` publisher with no local validation, timeout, or rate limiting. In a gateway bridging HTTP to robot motion, accepting arbitrary `TwistStamped` and publishing immediately is a safety hazard: malformed or excessive commands can produce runaway motion, starve other callbacks, or bypass watchdog expectations. Given the repository context, this file should enforce at least bounded linear/angular velocities and a timestamp freshness check before publishing.

**Suggestion:** Add defensive checks before publishing: reject stale messages, clamp or reject unsafe velocity magnitudes, and fail closed on invalid payloads. If final limits are configurable elsewhere, read them from ROS parameters here and enforce them centrally.

```suggestion
    def publish_cmd_vel(self, cmd_vel: TwistStamped) -> None:
        """Publish velocity command."""
        max_linear = 0.5
        max_angular = 1.0

        if abs(cmd_vel.twist.linear.x) > max_linear or abs(cmd_vel.twist.angular.z) > max_angular:
            raise ValueError("cmd_vel exceeds configured safety limits")

        self._cmd_vel_pub.publish(cmd_vel)
```

---

#### 🟠 High — Service clients are used without availability checks

All service calls immediately invoke `call_service_async(...)` without verifying that the underlying ROS service is available. On startup or during subsystem restarts, this creates avoidable timeout churn and turns transient dependency unavailability into repeated exceptions. For a gateway process, that degrades reliability and increases latency under failure. Since the dependency context does not show any helper guaranteeing readiness, this file should explicitly wait for required services before accepting requests.

**Suggestion:** After creating clients, block briefly for service readiness and fail fast if critical dependencies are unavailable. This should happen during initialization so the node does not start serving requests in a degraded state.

```suggestion
        self._update_route_service_client = self.create_client(
            UpdateRoute, "waypoint_manager/route/update_route"
        )

        critical_clients = [
            self._load_map_service_client,
            self._get_map_list_service_client,
            self._get_map_service_client,
            self._save_map_service_client,
            self._delete_map_service_client,
            self._edit_map_service_client,
            self._trigger_slam_service_client,
            self._check_slam_status_service_client,
            self._create_pose_service_client,
            self._capture_current_pose_service_client,
            self._create_route_service_client,
            self._delete_pose_service_client,
            self._delete_route_service_client,
            self._get_route_service_client,
            self._list_pose_service_client,
            self._list_route_service_client,
            self._update_pose_service_client,
            self._update_route_service_client,
        ]
        for client in critical_clients:
            if not client.wait_for_service(timeout_sec=3.0):
                raise RuntimeError(f"Required service unavailable: {client.srv_name}")
```

---


### 📄 `robot_gateway/http_bridge/routers/robot/map.py`

#### 🟠 High — DELETE uses request body for target resource

The delete endpoint identifies the map through a request body (`MapData`) instead of the URL path. Many HTTP clients, proxies, and gateways do not reliably support DELETE bodies, which makes this API fragile and can lead to accidental deletion failures in production. For a robot gateway, destructive operations must be unambiguous and interoperable. This should use a path parameter like the GET/PUT routes already do.

**Suggestion:** Move the target map identifier into the path and remove the body dependency from the handler signature.

```suggestion
@router.delete("/{map_name}", response_model=ApiResponse[dict], status_code=200)
@limiter.limit("30/minute")
async def delete_map(
```

---

#### 🟠 High — DELETE handler still depends on MapData body

Even if the route is fixed, the handler currently requires a full `MapData` payload and deletes using `map_cmd.map_name`. This is both semantically incorrect for DELETE and unsafe because the server accepts a larger mutable object than necessary for a destructive action. The handler should take only the path `map_name`, reducing attack surface and eliminating ambiguity.

**Suggestion:** Replace the body model with a path string parameter and keep the adapter dependency unchanged.

```suggestion
    request: Request,
    map_name: str,
    map_adapter: MapAdapter = Depends(get_map_adapter),
```

---

#### 🟠 High — DELETE response and action use body-derived map name

The delete implementation still reads `map_cmd.map_name` for both execution and response. This couples deletion to a request body and makes the route inconsistent with the resource-oriented path design used elsewhere in this file. It also increases the chance of deleting the wrong resource if the body and URL diverge after the route is corrected.

**Suggestion:** Use the path parameter as the single source of truth for the resource being deleted and echoed back to clients.

```suggestion
    await map_adapter.delete(map_name)
    response = {"map_name": map_name}
```

---

#### 🔴 Critical — Map name path parameter lacks validation

All endpoints accepting `map_name` directly forward an unvalidated string into the adapter layer. In map-management flows, names commonly become filesystem paths, ROS resource identifiers, or service arguments. Without explicit validation, malformed or path-like values can cause path traversal, adapter errors, or unsafe downstream behavior. Since the adapter implementation is not shown in the Dependency Context, the router should enforce a conservative allowlist at the API boundary.

**Suggestion:** Add FastAPI `Path` validation and constrain accepted map names to a safe pattern in each path-based endpoint.

```suggestion
from fastapi import APIRouter, Depends, Path, Request
```

---


### 📄 `robot_gateway/http_bridge/routers/robot/navigation.py`

#### 🔴 Critical — Unsafe navigation rate limit too high

The endpoint comments state a 30 requests/minute limit, but the actual limiter allows 50/minute on both motion start and stop. For robot motion control, permissive rate limits increase the risk of command flooding, actuator thrashing, and degraded watchdog behavior under client retries or abuse. This is a safety and reliability issue because these routes directly control robot movement.

**Suggestion:** Reduce the limiter to the documented 30/minute ceiling, or stricter if required by the control loop and watchdog design. The code and behavior must match to avoid unsafe command burst capacity.

```suggestion
@limiter.limit("30/minute")
```

---

#### 🟠 High — Start endpoint lacks payload validation guard

The route forwards the external MoveCommand payload directly into the navigation adapter with no visible validation or sanitization in this layer. The dependency context for common.schemas.api_schemas is empty, so there is no evidence here that MoveCommand enforces bounds, frame validity, or required fields. For a robot gateway, unvalidated motion targets can result in unsafe navigation goals, malformed downstream RPCs, or adapter exceptions that surface as 500s instead of controlled 4xx responses.

**Suggestion:** Add an explicit validation step before dispatching the command. Reject invalid or out-of-bounds motion requests with a client error, and only call the adapter after validation succeeds.

```suggestion
    cmd = navigation.validate_move_command(cmd)
    await navigation.start(cmd)
    return ApiResponse(action=request.url.path, payload=cmd)
```

---

#### 🔴 Critical — Stop command uses implicit zero-velocity defaults

Constructing CmdVel() with no explicit fields assumes the schema defaults to a safe full stop. The dependency context for common.schemas.robot is empty, so this assumption is not justified. If CmdVel has non-zero defaults, optional fields, or adapter-specific semantics, the stop route may fail to stop the robot deterministically. Motion stop commands must be explicit to avoid runaway behavior.

**Suggestion:** Construct an explicit zero-velocity command so the stop behavior is deterministic regardless of schema defaults.

```suggestion
    cmd_vel = CmdVel(linear_x=0.0, linear_y=0.0, angular_z=0.0)
    await navigation.stop(cmd_vel)
```

---

#### 🟠 High — Adapter failures are not translated to safe HTTP errors

Both endpoints await adapter methods directly with no error translation. Any downstream transport, timeout, or robot-state exception will likely propagate as a generic 500 response. In a robot gateway, command execution failures should be mapped to controlled HTTP errors with clear semantics so clients can back off or recover, and so unsafe partial-execution states are not masked by unhandled exceptions.

**Suggestion:** Wrap adapter calls in structured exception handling and convert known operational failures into explicit HTTPException responses. This prevents opaque server errors and improves reliability for command clients.

```suggestion
    try:
        await navigation.start(cmd)
    except Exception as exc:
        from fastapi import HTTPException
        raise HTTPException(status_code=502, detail=f"Failed to start navigation: {exc}")
    return ApiResponse(action=request.url.path, payload=cmd)
```

---


### 📄 `robot_gateway/http_bridge/routers/robot/pose.py`

#### 🟠 High — Unbounded query parameters enable resource exhaustion

The list endpoint accepts raw `offset` and `limit` integers without any validation. A client can send a very large `limit` or negative values, which can trigger expensive database scans, excessive memory usage, or undefined adapter behavior. For a robot gateway, this is a reliability and availability issue because API abuse can starve control-path resources. FastAPI supports declarative bounds validation at the router layer and it should be enforced here before delegating to `PoseAdapter.list(...)`.

**Suggestion:** Import `Query` and use it to constrain pagination and filter sizes. Enforce non-negative offset and a hard upper bound on limit to prevent abusive requests from reaching the adapter.

```suggestion
from fastapi import APIRouter, Depends, Query, Request
```

---

#### 🟠 High — List endpoint lacks pagination bounds enforcement

The current signature allows `offset` and `limit` to take arbitrary values, including negative numbers and very large page sizes. This creates a straightforward denial-of-service vector against storage and serialization layers and can increase latency for time-sensitive robot operations. The validation must happen at the HTTP boundary instead of relying on downstream adapter code that is not shown in the dependency context.

**Suggestion:** Add explicit query validation with safe defaults and maximums. This rejects invalid input before any downstream work and limits worst-case request cost.

```suggestion
    map_id: str = Query(default="", max_length=128),
    name_contains: str = Query(default="", max_length=128),
    tag_filter: str = Query(default="", max_length=128),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=100),
```

---

#### 🟡 Mid — Pose identifier is not validated at API boundary

Both delete and update endpoints accept arbitrary `pose_id` strings directly from the path. Without even minimal length validation, malformed or oversized identifiers can propagate into adapter/storage layers, increasing the risk of pathologically expensive lookups, log injection, or backend-specific parsing issues. Since this file is the public HTTP boundary, it should reject obviously invalid identifiers early.

**Suggestion:** Import `Path` and use bounded path validation for `pose_id`. This provides a first-line guardrail against malformed or abusive identifiers before adapter invocation.

```suggestion
from fastapi import APIRouter, Depends, Path, Query, Request
```

---

#### 🟡 Mid — Update/delete routes accept unchecked path IDs

The `pose_id` path parameter is declared as an unrestricted string in mutating endpoints. For commands that alter persisted robot pose data, accepting arbitrary identifiers is unsafe because it delegates validation entirely to downstream components whose contract is not visible in the dependency context. Enforcing simple structural constraints here improves security and avoids unnecessary backend work on invalid requests.

**Suggestion:** Constrain `pose_id` with `Path(...)` to reject empty or oversized identifiers at request parsing time. Apply this pattern to both `delete_pose` and `update_pose`.

```suggestion
    pose_id: str = Path(..., min_length=1, max_length=128),
```

---


### 📄 `robot_gateway/http_bridge/routers/robot/route.py`

#### 🟠 High — Unbounded pagination enables resource exhaustion

The list endpoint accepts arbitrary `offset` and `limit` values without FastAPI validation. A client can request extremely large limits or negative values, which can trigger expensive adapter/database scans, high memory use, and degraded latency for a robot control gateway. In this domain, API responsiveness matters for reliable command orchestration, so pagination inputs must be bounded at the HTTP layer before reaching `RouteAdapter.list(...)`.

**Suggestion:** Apply request validation constraints to reject negative offsets and cap the page size to a safe maximum.

```suggestion
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
```

---

#### 🟠 High — Route ID path parameter is not validated

`route_id` is passed directly from the URL into adapter methods for delete/get/update with no length or format validation. This allows malformed or oversized identifiers to propagate into lower layers, increasing the risk of injection into backend queries, log pollution, and unnecessary adapter work. Even if the adapter validates later, the router should fail fast on untrusted external input.

**Suggestion:** Constrain the path parameter to a reasonable length and require at least a non-empty identifier at the API boundary.

```suggestion
    route_id: str = Path(..., min_length=1, max_length=128),
```

---

#### 🟡 Mid — Mutating endpoints lack ownership-scoped throttling

All route mutations use a flat `30/minute` limit, but there is no visible per-tenant/per-user/per-robot scoping in this file. For a robot gateway, create/update/delete operations can change navigation behavior and should be protected against abusive bursts from a single caller. If the limiter falls back to IP-based keys, traffic behind NAT or internal proxies can either bypass intended controls or throttle unrelated clients. Mutating endpoints should use a stricter authenticated key function or a lower rate for safety-critical operations.

**Suggestion:** Use a stricter limit for write operations and ensure the limiter is keyed by authenticated client identity rather than only network source. If a custom key function exists in the limiter module, apply it here.

```suggestion
@limiter.limit("10/minute")
```

---

#### 🟡 Mid — Missing Query/Path imports break validation fixups

The module currently imports only `APIRouter`, `Depends`, and `Request` from FastAPI. Since this router should validate path and query inputs at the boundary, the required FastAPI parameter helpers are not imported. Without them, the endpoint signatures remain unguarded and the validation improvements cannot be implemented cleanly.

**Suggestion:** Import FastAPI parameter helper types so path/query validation can be expressed explicitly in the endpoint signatures.

```suggestion
from fastapi import APIRouter, Depends, Path, Query, Request
```

---


### 📄 `robot_gateway/http_bridge/routers/robot/slam.py`

#### 🟡 Mid — POST endpoint lacks explicit response schema

The POST handler advertises `response_model=ApiResponse[dict]` and returns only `{"active": status}`, while the request body is a full `SlamModel`. This creates an untyped, weakly validated API surface for a safety-relevant control path. For robot actuation endpoints, the response should be strongly typed and aligned with the actual semantic output so clients cannot mis-handle malformed payloads or undocumented fields.

**Suggestion:** Define and use a dedicated response schema for the SLAM trigger result instead of a raw dict generic. At minimum, switch the generic payload type to a concrete typed model representing the `active` field.

```suggestion
@router.post("/", response_model=ApiResponse[SlamModel], status_code=200)
```

---

#### 🟠 High — Control endpoint accepts unrestricted SlamModel input

The POST route directly accepts `slam_request: SlamModel` from external clients and forwards it to `slam.trigger(...)` without visible field-level restriction or sanitization. In a robot gateway, passing a broad internal model from public API to adapter logic is risky: clients may set status fields like `is_slam_running` or `is_slam_node_active` that should be adapter-derived, not user-controlled. This weakens input validation and can produce unsafe or inconsistent control behavior.

**Suggestion:** Replace the public request body with a minimal command schema containing only the intended operator input, e.g. a single `active: bool` field. Keep `SlamModel` for internal status/state exchange only.

```suggestion
    slam_request: dict,
```

---

#### 🟠 High — No error translation around adapter calls

Both endpoints await adapter methods directly with no exception handling. If `check_status()` or `trigger()` raises due to ROS/network/hardware faults, FastAPI will return a generic 500 and may leak internal failure details. For a robot gateway, adapter faults must be translated into deterministic HTTP errors with bounded information disclosure and predictable client behavior.

**Suggestion:** Wrap the adapter call in `try/except`, convert expected operational failures into `HTTPException` (e.g. 503/504), and avoid exposing raw backend exceptions. Apply the same pattern to `slam.trigger(...)`.

```suggestion
    try:
        slam_model: SlamModel = await slam.check_status()
    except Exception as exc:
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail="SLAM status unavailable") from exc
    response = {
        "is_slam_node_active": slam_model.is_slam_node_active,
        "is_slam_running": slam_model.is_slam_running,
    }

    return ApiResponse(action=request.url.path, payload=response)
```

---

#### 🟡 Mid — Unsafe state-changing route lacks idempotency semantics

The `POST /slam/` endpoint appears to toggle or activate/deactivate a long-running subsystem, but it uses a generic POST without any idempotency guard. In distributed fleet systems, retries from proxies/clients are common; replaying a state-changing command without explicit semantics can lead to repeated transitions or inconsistent robot state. For safety-critical control, the route should be modeled as an idempotent state set operation.

**Suggestion:** Use `PUT` for setting SLAM active/inactive state, or require an idempotency key if POST must be preserved. This makes retry behavior safer and more predictable for external control planes.

```suggestion
@router.put("/", response_model=ApiResponse[dict], status_code=200)
```

---


### 📄 `robot_gateway/http_bridge/routers/robot/status.py`

#### 🟠 High — Unused dependency may skip adapter initialization

Both endpoints inject `StatusAdapter`, but `handshake` never uses it. In FastAPI, dependency injection may still be intended to validate backend connectivity or trigger adapter-level health checks, but as written there is no actual verification that the robot or bridge is active. This makes the endpoint return success even when the adapter is unavailable, which is misleading for liveness/health semantics in a robot gateway.

**Suggestion:** Use the injected adapter to perform a lightweight status read so the handshake reflects actual robot availability. If no dedicated ping exists, reuse a cheap read such as battery status and only return success after it completes.

```suggestion
    await status.get_battery()
    return ApiResponse(action=request.url.path, payload="Robot is active.")
```

---

#### 🟠 High — No failure translation for backend status fetch

`await status.get_battery()` is returned directly without any exception handling. If the adapter raises due to transport failure, timeout, or hardware unavailability, FastAPI will surface a generic 500 response. For a robot gateway, backend communication failures should be translated into explicit upstream-facing errors to avoid ambiguous failures and support reliable watchdog/health monitoring.

**Suggestion:** Wrap the adapter call in targeted exception handling and return a deterministic HTTP error such as 503 for robot/backend unavailability. This prevents leaking internal exceptions and gives clients actionable status semantics.

```suggestion
    try:
        battery = await status.get_battery()
    except Exception as exc:
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail="Robot status unavailable") from exc
    return ApiResponse(action=request.url.path, payload=battery)
```

---


### 📄 `robot_gateway/http_bridge/routers/routers.py`

#### 🟡 Mid — Unused /robots router creates dead endpoint namespace

A second APIRouter is instantiated for the "/robots" prefix but never includes any routes and is not connected to the rest of this module. This creates an exported router object with no behavior, which is a reliability and integration risk because callers may mount the wrong router and silently expose no endpoints.

**Suggestion:** Remove the unused router until there is an actual collection-level API, or explicitly include routes on it in this module.

```suggestion
robot_router = APIRouter(prefix="/robot")
```

---


### 📄 `robot_gateway/http_bridge/statics/index.html`

#### 🟠 High — Health page leaks misleading operational status

This static page asserts that the system is online, active, and health checks have passed, but there is no dynamic linkage to actual gateway, robot, or watchdog state in this file. In a robot gateway, exposing a hard-coded healthy status is a reliability and safety issue because operators may infer the bridge and robot are safe to command even when backend services are degraded or disconnected.

**Suggestion:** Replace the hard-coded healthy wording with a neutral static landing message unless this page is wired to a real health endpoint. This avoids presenting false operational guarantees.

```suggestion
        <h1>Robot Gateway</h1>
        <p>Static status page. Verify live system health via the authenticated health API.</p>
        <div class="footer-text">
```

---

#### 🟡 Mid — No cache controls for status content

A status page served without cache directives can be cached by browsers or intermediaries and continue to display stale state. For operational monitoring, stale healthy responses are dangerous because they can mask outages or watchdog failures after recovery windows have expired.

**Suggestion:** Add explicit no-store and related cache-control meta tags so clients do not retain stale status content. This is especially important if the page is later made dynamic by the server.

```suggestion
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="Cache-Control" content="no-store, no-cache, must-revalidate, max-age=0">
    <meta http-equiv="Pragma" content="no-cache">
    <meta http-equiv="Expires" content="0">
    <title>Server Status - Live</title>
```

---

#### 🟡 Mid — Animated pulse ignores reduced-motion accessibility

The infinite pulse animation runs continuously with no reduced-motion fallback. On operator consoles or wallboards this can create unnecessary GPU churn and violate accessibility requirements for users who prefer reduced motion. For operational UIs, reducing unnecessary animation also improves stability on constrained HMI hardware.

**Suggestion:** Add a reduced-motion media query to disable the pulse animation when the client requests it. This preserves the visual design while avoiding unnecessary continuous animation.

```suggestion
        @keyframes pulse {
            0% { box-shadow: 0 0 0 0 rgba(76, 175, 80, 0.4); }
            70% { box-shadow: 0 0 0 15px rgba(76, 175, 80, 0); }
            100% { box-shadow: 0 0 0 0 rgba(76, 175, 80, 0); }
        }

        @media (prefers-reduced-motion: reduce) {
            .icon-wrapper {
                animation: none;
            }
        }
```

---


### 📄 `robot_gateway/launch/gateway_bringup.launch.py`

#### 🟠 High — Launch fails hard when package share is unavailable

`get_package_share_directory(package_name)` is executed immediately during launch description construction with no fallback or validation. If the package is missing, misinstalled, or the environment is not sourced correctly, the entire bringup crashes before any node starts. For a gateway responsible for robot connectivity, this creates a brittle startup path and prevents graceful failure diagnostics. The code should validate the resolved config path and fail with an explicit error message before passing it into node parameters.

**Suggestion:** Resolve the package share directory once, verify the params file exists, and raise a clear runtime error if not. This avoids opaque launch-time failures and makes deployment issues diagnosable.

```suggestion
    package_share_dir = get_package_share_directory(package_name)
    default_config_file = os.path.join(package_share_dir, "config", "params.yaml")
    if not os.path.isfile(default_config_file):
        raise RuntimeError(
            f"Parameter file not found: {default_config_file}"
        )
```

---

#### 🟡 Mid — No required parameter file enforcement for both bridges

Both `http_bridge` and `ws_bridge` are launched with a shared parameter file, but there is no enforcement that the supplied launch argument is valid at runtime. `LaunchConfiguration("params_file")` is only a substitution token; if a caller passes a nonexistent path, each bridge may start with missing defaults or fail differently depending on ROS2 parameter parsing behavior. For a robot gateway, inconsistent startup across command ingress paths is a reliability and safety risk.

**Suggestion:** Require the parameter file argument explicitly or keep the default but validate the path through launch-time existence checks before starting nodes. At minimum, make startup fail deterministically when the file is invalid.

```suggestion
            DeclareLaunchArgument(
                "params_file",
                default_value=default_config_file,
                description="Full path to the ROS2 parameters file for robot gateway (must exist)",
            ),
```

---

#### 🟠 High — No respawn policy for gateway communication processes

The launch file starts two external command ingress processes (`http_bridge` and `ws_bridge`) with no respawn behavior. If either crashes due to malformed external input, transient network failures, or internal exceptions, the robot gateway silently loses a control interface until manual intervention. For infrastructure bridging high-level fleet commands to robot hardware, this is a major reliability gap.

**Suggestion:** Enable controlled respawn with a short delay so transient failures do not permanently disable the HTTP ingress path. Apply the same policy to the WebSocket bridge.

```suggestion
            Node(
                package=package_name,
                executable="http_bridge",
                name="http_bridge",
                output="screen",
                emulate_tty=True,
                respawn=True,
                respawn_delay=2.0,
                parameters=[params_file],
            ),
```

---

#### 🟠 High — WebSocket bridge also lacks recovery on process failure

`ws_bridge` has the same single-point-of-failure behavior as `http_bridge`. In a real-time robot gateway, losing one ingress service can strand active clients or create split-brain behavior where one protocol remains available and the other does not. The launch configuration should recover crashed bridge processes automatically to preserve service continuity.

**Suggestion:** Add the same respawn policy to the WebSocket bridge node so both ingress services recover consistently from transient faults.

```suggestion
            Node(
                package=package_name,
                executable="ws_bridge",
                name="ws_bridge",
                output="screen",
                emulate_tty=True,
                respawn=True,
                respawn_delay=2.0,
                parameters=[params_file],
            ),
```

---


### 📄 `robot_gateway/launch/http_bridge.launch.py`

#### 🟠 High — HTTP bridge binds all interfaces by default

The launch file exposes the REST control bridge on 0.0.0.0 when HOST_IP is unset. For a robot control surface, this is an unsafe default because it publishes the command endpoint on every network interface, increasing the attack surface and making accidental remote access possible in misconfigured deployments. Given this file launches the HTTP bridge directly, the safer default is loopback-only and operators can explicitly override it when intentional external exposure is required.

**Suggestion:** Default to 127.0.0.1 so the service is local-only unless the deployment explicitly opts into network exposure via HOST_IP.

```suggestion
    host_ip = EnvironmentVariable("HOST_IP", default_value="127.0.0.1")
```

---


### 📄 `robot_gateway/launch/ws_bridge.launch.py`

#### 🟠 High — Package rename can break launch resolution

Changing the Node package from "bridge_interface" to "robot_gateway" is a functional runtime change, not a cosmetic edit. ROS launch resolves executables from the installed package index; if `ws_bridge` is still built/exported under `bridge_interface`, this launch file will fail at startup with package or executable lookup errors, taking down the real-time bridge entirely. The diff provides no accompanying build/install changes proving the executable moved packages, so this is a high-risk regression.

**Suggestion:** Keep the original package name unless the executable has been explicitly moved and installed under `robot_gateway`. If the migration is intentional, update the package metadata, install rules, and tests in the same change set before switching the launch target.

```suggestion
                package="bridge_interface",
```

---


### 📄 `robot_gateway/package.xml`

#### 🟡 Mid — Description still references old package purpose

The package name was changed from `bridge_interface` to `robot_gateway`, but the manifest description still says `Robot Bridge Interface Node`. In ROS package metadata, stale identity fields cause downstream confusion in tooling, release artifacts, and operator diagnostics, especially when multiple gateway/bridge packages coexist. This creates avoidable deployment and maintenance risk because the manifest no longer accurately describes the package being built and distributed.

**Suggestion:** Update the description to match the renamed package and its gateway role so package metadata remains internally consistent.

```suggestion
  <description>Robot Gateway Node</description>
```

---


### 📄 `robot_gateway/setup.cfg`


### 📄 `robot_gateway/setup.py`

#### 🟠 High — Removed executable breaks runtime entrypoint

The diff removes the `map_control` console script from package metadata. If this node is still referenced by launch files, service definitions, deployment manifests, or operator procedures, installations from this package will silently stop exposing that executable and fail at runtime with command-not-found/package launch errors. This is a packaging regression, not a cosmetic change, and should only be removed together with all downstream references in the same change set.

**Suggestion:** Keep the entry point until all launch/config/runtime references are removed in the same change. If the executable was intentionally renamed or moved, update the entry point rather than deleting it.

```suggestion
            "http_bridge = http_bridge.main:main",
            "ws_bridge = ws_bridge.main:main",
            "map_control = map_control.node:main",
```

---

#### 🟠 High — Static assets install path changed incompatibly

The package previously installed web assets under `share/<package>/static` and now installs from `http_bridge/statics/*` into `share/<package>/statics`. This changes both the source directory and the installed destination path. Any code, launch configuration, or deployment logic expecting assets under `.../static` will fail to locate UI/API resources at runtime. In a gateway package, that can disable operator control surfaces or HTTP endpoints after installation.

**Suggestion:** Preserve the installed destination path unless all runtime consumers have been updated in the same change. If the source folder moved, only update the glob source while keeping the package install path stable.

```suggestion
        ("share/" + package_name + "/static", glob.glob("http_bridge/statics/*")),
```

---


### 📄 `robot_gateway/test/http_bridge/test_map_routes.py`

#### 🟠 High — Invalid AsyncMock return values hide route serialization bugs

Several mocked adapter methods are configured to return type objects instead of concrete instances. `AsyncMock(return_value=list[str])` and `AsyncMock(return_value=MapData)` do not match the runtime contract the FastAPI routes serialize. This can let tests pass setup while masking real response-shape or encoder failures, and it weakens safety-critical confidence in HTTP route behavior under realistic payloads.

**Suggestion:** Return concrete values matching the adapter contract: a real list for `get_list` and a real `MapData` instance for `load`.

```suggestion
mock_adapter.get_list = AsyncMock(return_value=[])
mock_adapter.load = AsyncMock(return_value=MapData(map_name="/ws/maps/test.yaml"))
```

---

#### 🟠 High — Wrong endpoint in validation test breaks route coverage

The invalid-parameter test now posts to `/robot/map`, while the success path uses `/robot/map/load`. If the route is defined only on `/robot/map/load`, this test no longer validates request-body schema handling for the load endpoint and may fail for the wrong reason (404/405 instead of 422). That creates a false sense of coverage for input validation on an externally exposed API surface.

**Suggestion:** Call the same load endpoint used by the success case so the test actually exercises validation on the intended route.

```suggestion
response = client.post("/robot/map/load", json=payload)
```

---

#### 🟡 Mid — Map retrieval assertion couples to mock output instead of request input

The test asserts `mock_adapter.get` was called with `test_map_data.map_name`, which is the mocked return value, not the route parameter. If the handler accidentally passes the wrong argument but the mock is adjusted to match, the test still passes. For route correctness, the assertion must validate that the path parameter `test_map` was forwarded to the adapter unchanged.

**Suggestion:** Assert against the request path variable directly so the test verifies parameter propagation from HTTP layer to adapter.

```suggestion
mock_adapter.get.assert_called_once_with("test_map")
```

---

#### 🟡 Mid — Update route test does not validate forwarded map payload

The update success test only checks that `update()` was called once, but not with the expected `MapData`. A handler bug that mutates fields, drops payload data, or constructs the wrong object would still pass. For a robot gateway, payload integrity matters because incorrect map content can affect navigation reliability.

**Suggestion:** Assert the adapter receives the exact `MapData` object content expected by the route to catch request parsing or transformation regressions.

```suggestion
mock_adapter.update.assert_called_once_with(map_data)
```

---


### 📄 `robot_gateway/test/http_bridge/test_navigation_routes.py`

#### 🟠 High — Shared mock state makes tests order-dependent

The module-level `mock_adapter` and `client` are reused across all tests, but assertions use `assert_called_once_with` / `assert_called_once`. Once one test invokes `start` or `stop`, later tests can fail purely because call history persists, not because the route is broken. This creates nondeterministic, order-dependent test behavior and weakens regression detection for navigation safety paths.

**Suggestion:** Reset the shared mock before each test so call-count assertions remain isolated. A lightweight autouse fixture is sufficient and avoids rewriting all tests.

```suggestion
client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_mock_adapter():
    mock_adapter.reset_mock()
```

---

#### 🟡 Mid — Loose MagicMock adapters can mask wiring errors

Only `navigation_adapter` is created with a spec. The other injected adapters are bare `MagicMock()` instances, so any unexpected attribute access or wrong method name during app startup or route registration will silently succeed. In a gateway that wires multiple robot control surfaces, this can hide broken dependency contracts and let tests pass while production fails.

**Suggestion:** Use autospecced mocks for every injected adapter class, or at minimum provide strict stub objects with only the attributes the app expects. This makes dependency mismatches fail fast during test setup.

```suggestion
adapters = {
    "navigation_adapter": mock_adapter,
    "status_adapter": MagicMock(spec_set=[]),
    "map_adapter": MagicMock(spec_set=[]),
    "slam_adapter": MagicMock(spec_set=[]),
    "pose_adapter": MagicMock(spec_set=[]),
    "route_adapter": MagicMock(spec_set=[]),
}
```

---

#### 🟡 Mid — Test now hard-codes route path as API contract

The assertions were changed from semantic action names (`move`, `stop`) to literal HTTP paths (`/robot/navigation/start`, `/robot/navigation/stop`). This couples the test to transport-layer routing instead of the command semantics. If the server keeps semantic `action` values while changing only the URL prefix, these tests will fail incorrectly; conversely, if `action` is accidentally populated from the request path, the test will pass while the API contract regresses.

**Suggestion:** Assert the semantic action value returned by the API, not the URL path. If the contract intentionally changed, validate that in a dedicated schema/contract test rather than in route behavior tests.

```suggestion
assert response["action"] == "move"
```

---

#### 🟠 High — Stop route test sends irrelevant payload, weakening validation

The stop command test posts a body `{"x": 0.5, "y": 0.1}` but only validates status and that `mock_adapter.stop()` was called. If `/robot/navigation/stop` is intended to be bodyless, this test permits unvalidated external input on a control endpoint; if it requires a schema, the test does not verify parsing at all. For a robot stop path, tests should be strict about rejecting unexpected payloads rather than normalizing them silently.

**Suggestion:** Exercise the stop endpoint without a payload, or add a negative test asserting unexpected body fields are rejected. This better protects the control surface contract.

```suggestion
response = client.post("/robot/navigation/stop")
```

---


### 📄 `robot_gateway/test/http_bridge/test_status_routes.py`

#### 🟠 High — Global TestClient shares mutable mocks across tests

The module-level app/client and shared MagicMock create hidden inter-test coupling. Even with a fixture resetting the mock, dependency overrides and app state remain process-global, which can break under parallel execution or when additional tests mutate adapters/overrides. For gateway route tests, isolation matters because stale overrides can mask routing and dependency-injection regressions.

**Suggestion:** Create the app and TestClient per test (or via a fixture) so dependency overrides and adapter mocks are isolated. This prevents cross-test state leakage and makes route behavior deterministic.

```suggestion
@pytest.fixture()
def client():
    app = create_app(adapters)
    app.dependency_overrides[get_status_adapter] = lambda: mock_adapter
    with TestClient(app) as test_client:
        yield test_client
```

---

#### 🟡 Mid — Tests may pass with incomplete adapter wiring

The test constructs the application with a plain dictionary of MagicMocks for all adapters, but only status_adapter is spec-bound. If create_app validates adapter interfaces or accesses required methods during startup, these untyped MagicMocks can silently absorb invalid calls and allow the test to pass while production wiring is broken. This weakens regression coverage around dependency injection in a safety-critical gateway.

**Suggestion:** Use interface-spec'd mocks for every injected adapter, or construct only the minimum valid app wiring required by the status routes. At minimum, avoid bare MagicMock objects for top-level dependencies consumed by create_app.

```suggestion
adapters = {
    "navigation_adapter": MagicMock(spec_set=[]),
    "status_adapter": mock_adapter,
    "map_adapter": MagicMock(spec_set=[]),
    "slam_adapter": MagicMock(spec_set=[]),
    "pose_adapter": MagicMock(spec_set=[]),
    "route_adapter": MagicMock(spec_set=[]),
}
```

---

#### 🟡 Mid — Route assertion hard-codes transport path as action contract

The test now asserts that the response action equals the HTTP route string. That couples the API contract to transport-layer path naming rather than business action semantics. If the route is versioned, prefixed, or mounted differently, the test fails even though the status handler behavior is correct. This makes the test brittle and can obscure real regressions in the battery status payload or adapter invocation.

**Suggestion:** Assert a stable semantic action if that is the API contract, or remove the action assertion if route formatting is not part of the status payload contract. Avoid binding the response schema to mount path details.

```suggestion
    assert response["action"] == "get_battery"
```

---


### 📄 `robot_gateway/test/ws_bridge/test_ws_integration.py`

#### 🟠 High — Using current event loop makes tests flaky

These fixtures/tests bind StreamAdapter to whatever loop `asyncio.get_event_loop()` returns. Under `pytest.mark.asyncio`, fixture creation can occur outside the running test loop, especially with newer asyncio policies, causing callbacks/tasks to be attached to a different loop than the one executing the test. That leads to nondeterministic failures, missed broadcasts, and hard-to-reproduce race conditions in async integration coverage.

**Suggestion:** Use the currently running loop from an async fixture, or inject the pytest event loop fixture so the adapter is always bound to the same loop used by the test.

```suggestion
loop = event_loop
    return StreamAdapter(mock_ros_node, connection_manager, loop)
```

---

#### 🟠 High — Fixture signature missing event loop dependency

The `stream_adapter` fixture now depends on an event loop but does not declare one. This prevents reliably wiring the adapter to pytest's managed loop and blocks the fix for loop affinity bugs. As written, the fixture implicitly reaches for global loop state, which is exactly what causes async test instability.

**Suggestion:** Accept pytest's loop fixture explicitly so the adapter is created against the test-managed event loop.

```suggestion
def stream_adapter(mock_ros_node, connection_manager, event_loop):
```

---

#### 🟡 Mid — Map and scan coverage removed despite new subscriptions

The diff adds `OccupancyGrid` and `LaserScan` imports plus mock callback registration for map and scan, but no integration test verifies those topics are actually wired and broadcast. This creates a regression hole: the adapter/server can silently stop forwarding map or scan data while tests still pass. For a robot gateway, untested sensor-stream forwarding is a reliability risk because downstream navigation consumers depend on those feeds.

**Suggestion:** Either add integration tests that exercise map/scan callback registration and websocket broadcast paths, or remove the unused imports and callback scaffolding until those paths are actually covered. The minimal corrective change in this file is to stop implying coverage that does not exist.

```suggestion
from nav_msgs.msg import Odometry
```

---


### 📄 `robot_gateway/test/ws_bridge/test_ws_routing.py`

#### 🟠 High — Removed joy route coverage hides control-path regressions

This diff deletes all WebSocket tests for `/ws/control/joy`, including success, defaulting, multi-command, and failure handling. For a robot gateway, the control channel is safety-critical: removing these tests eliminates coverage of command routing, adapter invocation, and error propagation for operator input. If the endpoint still exists, regressions in validation, rate limiting, or watchdog/error behavior will go undetected. If the endpoint was intentionally removed, the test file should explicitly verify that it is unavailable rather than silently dropping coverage.

**Suggestion:** Keep the new snapshot mock, but also restore the joy-control adapter mock so the deleted control-route tests can remain valid or be replaced with an explicit deprecation assertion.

```suggestion
mock_adapter.get_snapshot = MagicMock(return_value=None)
mock_adapter.publish_joy = AsyncMock(return_value=True)
```

---

#### 🟡 Mid — Fixture reset no longer restores joy adapter state

The autouse fixture now resets only `get_snapshot` and no longer reinstalls `publish_joy`. Any remaining or future control-route tests in this module will inherit stale mock state across cases, causing order-dependent behavior and masking failures. In test suites validating robot motion commands, deterministic isolation is required to reliably catch command handling regressions.

**Suggestion:** Restore `publish_joy` inside the reset fixture alongside `get_snapshot` so each test starts from a clean adapter state.

```suggestion
mock_adapter.get_snapshot = MagicMock(return_value=None)
    mock_adapter.publish_joy = AsyncMock(return_value=True)
```

---


### 📄 `robot_gateway/ws_bridge/adapter.py`

#### 🔴 Critical — Joystick commands are published without validation or clamping

This method forwards externally supplied WebSocket payload fields directly into a robot control message. That is a safety and security issue: malformed types, oversized values, or unexpected payloads can propagate into the ROS control path and cause undefined robot motion or downstream serialization/runtime failures. For a robotic gateway, external motion inputs must be validated and bounded before publishing.

**Suggestion:** Validate that the payload is a dict, coerce numeric/button fields safely, and clamp analog axes to a bounded range before publishing. Reject or default invalid values rather than forwarding them verbatim.

```suggestion
        if not isinstance(command, dict):
            return

        def _axis(name: str) -> float:
            try:
                value = float(command.get(name, 0.0))
            except (TypeError, ValueError):
                return 0.0
            return max(-1.0, min(1.0, value))

        def _button(name: str) -> int:
            value = command.get(name, 0)
            return 1 if value in (1, True, "1", "true", "True") else 0

        joy_msg.lx = _axis("x")
        joy_msg.ly = _axis("y")
        joy_msg.up = _button("up")
        joy_msg.down = _button("down")
        joy_msg.left = _button("left")
        joy_msg.right = _button("right")
```

---

#### 🔴 Critical — No rate limiting on UI joystick publishing

The new joystick publish path has no throttling or watchdog behavior. A fast or malicious client can flood /joy_ui with high-frequency commands, starving the event loop, saturating ROS transport, or causing unstable robot actuation. For a gateway controlling hardware, command ingress must be rate limited at the adapter boundary.

**Suggestion:** Add a monotonic-time based publish interval guard before sending commands. This should drop or coalesce excessive command rates to a safe upper bound.

```suggestion
        now = asyncio.get_running_loop().time()
        last_publish = getattr(self, "_last_joy_publish_time", 0.0)
        min_interval = getattr(self, "_joy_publish_min_interval", 0.05)
        if now - last_publish < min_interval:
            return
        self._last_joy_publish_time = now
        self.node.publish_joy_ui(joy_msg)
```

---

#### 🟠 High — Threadsafe broadcast futures are ignored

Both ROS callbacks schedule coroutines from another thread using asyncio.run_coroutine_threadsafe but discard the returned Future. Any exception raised by manager.broadcast will be silently lost, causing data delivery failures with no observability and potentially unbounded accumulation of failed tasks. In a real-time gateway this degrades reliability and complicates recovery.

**Suggestion:** Capture the returned Future and attach a done callback that consumes result() so broadcast failures are surfaced and do not remain silent.

```suggestion
        future = asyncio.run_coroutine_threadsafe(
            self.manager.broadcast("scan", map_dict), self.loop
        )
        future.add_done_callback(lambda f: f.result())
```

---

#### 🟡 Mid — Snapshot access races on mutable ROS state

get_snapshot reads self.node.map, self.node.odom, and self.node.scan directly with no synchronization, while those fields are likely updated asynchronously by ROS callbacks. That creates a race where the object reference can change mid-read or expose partially updated state to WebSocket clients. Returning cached snapshots should use a stable local reference per branch at minimum.

**Suggestion:** Read each node field once into a local variable before converting it. If stronger thread safety is available in the node implementation, use its lock or accessor instead.

```suggestion
        if topic == "map":
            msg = self.node.map
            if msg is not None:
                return map_to_dict(msg)
        if topic == "odom":
            msg = self.node.odom
            if msg is not None:
                return odom_to_dict(msg)
        if topic == "scan":
            msg = self.node.scan
            if msg is not None:
                return scan_to_dict(msg)
```

---


### 📄 `robot_gateway/ws_bridge/main.py`

#### 🟠 High — Hard-coded connection limit bypasses safe configuration

Instantiating ConnectionManager with a literal `20` in the entrypoint hard-codes an operational safety limit that should remain externally configurable. In a robot gateway, connection caps directly affect resource exhaustion behavior and fail-safe degradation under load. This change can silently override environment-, launch-, or node-level tuning and create either denial of service from an overly low cap or instability from an incorrect assumed default. The limit should come from validated runtime configuration owned by the node or application config, not embedded in main.

**Suggestion:** Read the connection limit from validated configuration exposed by the ROS node or a dedicated config source, and pass that value into ConnectionManager. If no config is available, preserve constructor defaults instead of forcing a magic number.

```suggestion
    manager = ConnectionManager(ws_bridge_node.max_connections)
```

---

#### 🔴 Critical — Origin allowlist is passed without defensive validation

`ws_bridge_node.allow_origins` is now injected directly into `create_app`, but there is no visible validation or normalization at this call site. If the ROS parameter is unset, malformed, or permissive (for example `*` or a string where a list is expected), the gateway can unintentionally disable origin protections and expose robot control endpoints cross-origin. Since this file wires the security boundary, it should fail closed before constructing the app.

**Suggestion:** Validate that `allow_origins` is a non-empty list/tuple/set of explicit origins before passing it to `create_app`, and reject wildcard or invalid values at startup.

```suggestion
    allow_origins = ws_bridge_node.allow_origins
    if not isinstance(allow_origins, (list, tuple, set)) or not allow_origins or any(origin == "*" for origin in allow_origins):
        raise ValueError("allow_origins must be a non-empty collection of explicit origins")
    app = create_app(manager, adapter, list(allow_origins))
```

---


### 📄 `robot_gateway/ws_bridge/node.py`

#### 🔴 Critical — Allow-all CORS origin enables unauthorized control

The new default `allow_origin` value of `['*']` permits any web origin to connect to the gateway. In a robot control bridge, this is a security-critical exposure because any hostile page opened in an operator browser can issue websocket traffic and potentially drive the robot or flood telemetry. Given this node stores and publishes control-related messages, the default must be deny-by-default or restricted to explicit trusted origins.

**Suggestion:** Default to an empty allowlist so deployments must explicitly configure trusted origins. If wildcard support is truly needed, gate it behind an explicit insecure-development setting elsewhere rather than enabling it by default.

```suggestion
self.declare_parameter("allow_origin", [])
```

---

#### 🟠 High — Joystick publisher type changed without compatibility guard

The publisher message type was changed from `sensor_msgs.msg.Joy` to `esp_joystick_interfaces.msg.JoystickInfo` on the same `/joy` topic. This is a breaking wire-level change: ROS topics are strongly typed, and any existing consumers expecting `Joy` will fail to connect. For a robot gateway, that can silently break teleoperation or safety interlocks that subscribe to `/joy`. The dependency context provides no evidence of `Joy` consumers being migrated in lockstep, so changing the topic type in place is unsafe.

**Suggestion:** Do not repurpose an established topic with a different message type. Publish `JoystickInfo` on a new dedicated topic, or keep `/joy` as `Joy` and add a separate publisher for the new message type.

```suggestion
self.joy_publisher = self.create_publisher(JoystickInfo, "/joy_ui", 10)
```

---

#### 🟠 High — LaserScan subscription uses unreliable default QoS

The `/scan` subscription is created with a raw integer depth, which relies on implicit default QoS. Laser scanners commonly publish with sensor-data QoS semantics, and a generic depth-only subscription can mismatch reliability/history settings or incur unnecessary latency under load. In a real-time robot gateway, scan data should use explicit low-latency sensor QoS to avoid dropped connections or stale obstacle data affecting downstream safety decisions.

**Suggestion:** Use the ROS sensor data QoS profile explicitly for `/scan` subscriptions so the node matches common publishers and minimizes latency for obstacle telemetry.

```suggestion
self.create_subscription(LaserScan, "/scan", self._scan_callback, qos_profile_sensor_data)
```

---

#### 🟠 High — Unbounded callback failures can break stream processing

Each message callback iterates user-registered callbacks without isolating exceptions. If one downstream callback raises, remaining callbacks will not run and the exception can propagate into the executor, disrupting telemetry fan-out. In a bridge service, a single faulty websocket client handler must not block odom/map/scan delivery to other consumers or destabilize the node.

**Suggestion:** Wrap callback invocation in `try/except`, log failures, and continue dispatching to other listeners. Apply the same hardening to odom and map callback loops as well.

```suggestion
for callback in self._scan_callbacks:
            try:
                callback(msg)
            except Exception as exc:
                self.get_logger().error(f"scan callback failed: {exc}")
```

---


### 📄 `robot_gateway/ws_bridge/ws_server.py`

#### 🔴 Critical — Unauthenticated joy control over WebSocket

The new `joy` topic turns this endpoint from read-only telemetry into a robot control surface, but there is no authentication or authorization check before accepting the connection and forwarding commands to `publish_joy_ui`. Any client that can reach this route and satisfy CORS/origin handling can inject motion/control commands. For a robot gateway, this is a must-fix safety and security issue because it enables unauthorized actuation.

**Suggestion:** Require an authenticated token or equivalent credential before accepting `joy` connections, and reject unauthorized clients with a policy violation close code. The auth check must happen before `manager.connect(...)` so the socket is never accepted for untrusted clients.

```suggestion
        if topic == "joy":
            token = websocket.headers.get("authorization")
            if not token or not app.state.adapter.validate_joy_client(token):
                await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Unauthorized")
                return

        is_accepted = await manager.connect(websocket, topic)

        if not is_accepted:
            return
```

---

#### 🔴 Critical — No validation or rate limiting for joy commands

The handler deserializes arbitrary JSON and forwards it directly to `publish_joy_ui` with no schema validation, bounds checking, or message rate limiting. This allows malformed payloads, oversized structures, or extremely high-frequency command streams to reach the adapter, creating both safety risk (runaway or invalid robot commands) and denial-of-service risk on the control path.

**Suggestion:** Validate that the decoded payload is a dict with an expected shape and clamp/reject invalid values before publishing. Also add per-connection rate limiting so a client cannot flood the control channel. Invalid or abusive clients should be disconnected with a policy violation.

```suggestion
                if topic == "joy":
                    try:
                        command = json.loads(data)
                        if not isinstance(command, dict):
                            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid joy payload")
                            return
                        if not app.state.adapter.validate_joy_command(command):
                            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid joy command")
                            return
                        if not app.state.adapter.check_joy_rate_limit(websocket, command):
                            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Joy rate limit exceeded")
                            return
                        app.state.adapter.publish_joy_ui(command)

                    except json.JSONDecodeError:
                        logger.error("Joy topic error: Client sent invalid JSON")
                        continue
                    except Exception as e:
                        logger.error(f"Error publishing joy command: {e}")
                        continue
```

---

#### 🟠 High — Connection leak on unexpected WebSocket errors

The generic exception path logs an error but does not guarantee the underlying socket is closed. Removing the connection from `active_connections` is not sufficient; the transport may remain open until timeout, leaking resources and allowing clients to keep a broken session alive. Under repeated failures this degrades reliability and capacity enforcement.

**Suggestion:** Explicitly close the WebSocket in the unexpected-exception path before removing it from the manager. Use an internal error code to terminate the session deterministically.

```suggestion
        except Exception as e:
            logger.error(f"Unexpected WebSocket error on topic '{topic}': {e}")
            await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
            manager.disconnect(websocket, topic)
```

---

#### 🟠 High — CORS origin change can silently disable origin protections

The previous code sourced allowed origins from centralized configuration. The new signature accepts `allow_origin` directly and applies it with no validation or safe default. If callers pass `['*']`, an empty list, or user-controlled values, browser-origin protections for WebSocket-associated HTTP handling become inconsistent across deployments. For a gateway exposing robot topics, origin policy should remain centrally constrained rather than delegated ad hoc.

**Suggestion:** Restore a trusted configuration source or validate the provided origins defensively before wiring middleware. Reject wildcard origins for deployments that expose control topics.

```suggestion
def create_app(manager: ConnectionManager, adapter: StreamAdapter, allow_origin: list[str]) -> FastAPI:
    """Create FastAPI app with WebSocket endpoints."""
    if not allow_origin or "*" in allow_origin:
        raise ValueError("allow_origin must be an explicit non-wildcard origin list")
    app = FastAPI()
```

---


### 📄 `robot_gateway_interfaces/CMakeLists.txt`

#### 🔴 Critical — ROS interface generation removed

The diff deletes the only rosidl_generate_interfaces(...) invocation. In an interface package, this prevents ROS service definitions from being generated and exported at build time, which will break downstream packages that depend on these service types. This is a functional build/runtime regression, not a cosmetic rename.

**Suggestion:** Restore rosidl_generate_interfaces with the service files before the testing block so the package continues generating its declared ROS interfaces.

```suggestion
# find_package(<dependency> REQUIRED)

rosidl_generate_interfaces(${PROJECT_NAME}
  "srv/GetMapList.srv"
  "srv/GetMap.srv"
  "srv/ChangeMap.srv"
  "srv/SaveMap.srv"
  "srv/EditMap.srv"
)

if(BUILD_TESTING)
```

---

#### 🟠 High — Package rename likely breaks dependent package resolution

Changing the CMake project name from bridge_interface_interfaces to robot_gateway_interfaces changes the generated ROS package/interface target name. Any downstream package.xml, CMakeLists.txt, or source code still referencing the old package will fail to resolve generated interfaces. Unless all dependents were updated atomically, this is a breaking API change.

**Suggestion:** Keep the original project name unless the repository has been fully migrated, or coordinate this rename with matching updates to all dependent packages and manifests in the same change set.

```suggestion
project(bridge_interface_interfaces)
```

---


### 📄 `robot_gateway_interfaces/package.xml`

#### 🟠 High — License field left invalid for release

The package manifest still contains a placeholder license value. In ROS2, package.xml metadata is consumed by build, distribution, and compliance tooling; leaving `TODO: License declaration` makes the package legally ambiguous and can block release pipelines, downstream redistribution, and automated validation. This is a must-fix manifest correctness issue, not a documentation nit.

**Suggestion:** Replace the placeholder with the actual SPDX-compatible license identifier used by the repository.

```suggestion
  <license>Apache-2.0</license>
```

---


### 📄 `ros_entrypoint.sh`



---
*Generated by LangGraph PR Review Bot*