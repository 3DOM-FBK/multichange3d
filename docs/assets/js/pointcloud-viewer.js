(function () {
  "use strict";

  // =========================================
  // Scene configuration
  // =========================================
  var SCENES = [
    { id: "office",                    name: "Office",                   sensor: "RGB-D",           rx:  50, ry: -45, rz: -150 },
    { id: "open_space_rgbd",           name: "Open Space (RGB-D)",       sensor: "RGB-D",           rx:  55, ry:  45, rz:  155 },
    { id: "open_space_mls",            name: "Open Space (MLS)",         sensor: "MLS",             rx:  45, ry:   0, rz:  180 },
    { id: "underground_car_parking",   name: "Underground Car Parking",  sensor: "MLS",             rx: -45, ry:  30, rz:   30 },
    { id: "bike_parking_construction", name: "Bike Parking Construction",sensor: "MLS",             rx:  60, ry:  30, rz:  160 },
    { id: "vineyard",                  name: "Vineyard",                 sensor: "MLS",             rx: -35, ry: -40, rz:  -40 },
    { id: "classroom",                 name: "Classroom",                sensor: "TLS",             rx:  50, ry: -35, rz: -150 },
    { id: "meeting_room",              name: "Meeting Room",             sensor: "TLS",             rx:  50, ry: -35, rz: -150 },
    { id: "landslide",                 name: "Landslide",                sensor: "UAV Camera",      rx:  60, ry:  30, rz:  170 },
    { id: "city_airborne_camera",      name: "City (Airborne Camera)",   sensor: "Airborne Camera", rx:  45, ry:  35, rz:  150 },
    { id: "city_airborne_lidar",       name: "City (Airborne LiDAR)",    sensor: "Airborne LiDAR",  rx:  45, ry:  35, rz:  150 },
  ];

  var BASE_PATH = "assets/clouds";

  // =========================================
  // Green-yellow-red colormap (by Z height)
  // t=0 → green, t=0.5 → yellow, t=1 → red
  // =========================================
  function greenYellowRed(t) {
    t = Math.max(0, Math.min(1, t));
    var r = Math.min(1, 2 * t);
    var g = Math.min(1, 2 * (1 - t));
    return [r, g, 0];
  }

  // =========================================
  // PLY type definitions
  // =========================================
  var TYPE_INFO = {
    char: { size: 1, getter: "getInt8" },
    int8: { size: 1, getter: "getInt8" },
    uchar: { size: 1, getter: "getUint8" },
    uint8: { size: 1, getter: "getUint8" },
    short: { size: 2, getter: "getInt16" },
    int16: { size: 2, getter: "getInt16" },
    ushort: { size: 2, getter: "getUint16" },
    uint16: { size: 2, getter: "getUint16" },
    int: { size: 4, getter: "getInt32" },
    int32: { size: 4, getter: "getInt32" },
    uint: { size: 4, getter: "getUint32" },
    uint32: { size: 4, getter: "getUint32" },
    float: { size: 4, getter: "getFloat32" },
    float32: { size: 4, getter: "getFloat32" },
    double: { size: 8, getter: "getFloat64" },
    float64: { size: 8, getter: "getFloat64" },
    int64:  { size: 8, getter: "getFloat64" },   // read as double (same width)
    uint64: { size: 8, getter: "getFloat64" },
  };

  // =========================================
  // PLY parser — handles ASCII and binary,
  // reads RGB vertex colors or intensity
  // =========================================
  function parsePLY(buffer) {
    var bytes = new Uint8Array(buffer);

    // Locate "end_header" in the byte stream
    var target = [101, 110, 100, 95, 104, 101, 97, 100, 101, 114]; // "end_header"
    var headerEndByte = -1;
    var searchLimit = Math.min(bytes.length, 65536);
    for (var i = 0; i < searchLimit; i++) {
      if (bytes[i] === target[0]) {
        var match = true;
        for (var j = 1; j < target.length; j++) {
          if (bytes[i + j] !== target[j]) {
            match = false;
            break;
          }
        }
        if (match) {
          headerEndByte = i + target.length;
          // Skip past \r and/or \n after end_header
          while (
            headerEndByte < bytes.length &&
            (bytes[headerEndByte] === 10 || bytes[headerEndByte] === 13)
          ) {
            headerEndByte++;
          }
          break;
        }
      }
    }
    if (headerEndByte === -1) throw new Error("Invalid PLY: no end_header");

    // Parse header text
    var headerText = new TextDecoder("ascii").decode(
      bytes.subarray(0, headerEndByte)
    );
    var lines = headerText
      .split(/\r?\n/)
      .map(function (l) {
        return l.trim();
      })
      .filter(function (l) {
        return l.length > 0;
      });

    var format = "ascii";
    var vertexCount = 0;
    var inVertexElement = false;
    var properties = [];

    for (var li = 0; li < lines.length; li++) {
      var line = lines[li];
      if (line.startsWith("format ")) {
        format = line.split(/\s+/)[1];
      } else if (line.startsWith("element vertex ")) {
        vertexCount = parseInt(line.split(/\s+/)[2], 10);
        inVertexElement = true;
      } else if (line.startsWith("element ") && inVertexElement) {
        inVertexElement = false;
      } else if (line.startsWith("property ") && inVertexElement) {
        var parts = line.split(/\s+/);
        if (parts[1] === "list") continue;
        var info = TYPE_INFO[parts[1].toLowerCase()];
        if (info) {
          properties.push({ name: parts[2].toLowerCase(), type: parts[1], size: info.size, getter: info.getter });
        } else {
          // Unknown type — record a placeholder so binary stride stays correct.
          // Default to 4 bytes; real unknown types may still misalign, but this
          // is better than silently dropping bytes.
          properties.push({ name: parts[2].toLowerCase(), type: parts[1], size: 4, getter: "getFloat32" });
        }
      }
    }

    if (vertexCount === 0) throw new Error("PLY has no vertices");

    // Build property index and byte stride (names already lowercased)
    var propIdx = {};
    var byteStride = 0;
    for (var pi = 0; pi < properties.length; pi++) {
      propIdx[properties[pi].name] = pi;
      properties[pi].offset = byteStride;
      byteStride += properties[pi].size;
    }

    var hasRGB =
      "red" in propIdx && "green" in propIdx && "blue" in propIdx;
    var intensityKey = "intensity" in propIdx
      ? "intensity"
      : "scalar_Intensity" in propIdx
        ? "scalar_Intensity"
        : "scalar_intensity" in propIdx
          ? "scalar_intensity"
          : null;
    var hasIntensity = intensityKey !== null;

    var positions = new Float32Array(vertexCount * 3);
    var colors = new Float32Array(vertexCount * 3);

    var xi = propIdx["x"],
      yi = propIdx["y"],
      zi = propIdx["z"];

    if (format === "ascii") {
      var dataText = new TextDecoder("ascii").decode(
        bytes.subarray(headerEndByte)
      );
      var dataLines = dataText.trim().split(/\r?\n/);

      for (var v = 0; v < vertexCount && v < dataLines.length; v++) {
        var vals = dataLines[v].trim().split(/\s+/);
        positions[v * 3]     = parseFloat(vals[xi]);
        positions[v * 3 + 1] = parseFloat(vals[yi]);
        positions[v * 3 + 2] = parseFloat(vals[zi]);
        if (hasRGB) {
          var cs = properties[propIdx["red"]].size === 1 ? 1 / 255 : 1;
          colors[v * 3]     = parseFloat(vals[propIdx["red"]])   * cs;
          colors[v * 3 + 1] = parseFloat(vals[propIdx["green"]]) * cs;
          colors[v * 3 + 2] = parseFloat(vals[propIdx["blue"]])  * cs;
        }
      }
    } else {
      // binary_little_endian or binary_big_endian
      var isLE = format === "binary_little_endian";
      var view = new DataView(buffer, headerEndByte);
      var isColorByte = hasRGB ? properties[propIdx["red"]].size === 1 : false;
      var csBin = isColorByte ? 1 / 255 : 1;

      for (var v2 = 0; v2 < vertexCount; v2++) {
        var base = v2 * byteStride;
        positions[v2 * 3]     = view[properties[xi].getter](base + properties[xi].offset, isLE);
        positions[v2 * 3 + 1] = view[properties[yi].getter](base + properties[yi].offset, isLE);
        positions[v2 * 3 + 2] = view[properties[zi].getter](base + properties[zi].offset, isLE);
        if (hasRGB) {
          var rp = properties[propIdx["red"]];
          var gp = properties[propIdx["green"]];
          var bp = properties[propIdx["blue"]];
          colors[v2 * 3]     = view[rp.getter](base + rp.offset, isLE) * csBin;
          colors[v2 * 3 + 1] = view[gp.getter](base + gp.offset, isLE) * csBin;
          colors[v2 * 3 + 2] = view[bp.getter](base + bp.offset, isLE) * csBin;
        }
      }
    }

    // ---- Colour by Z (green-yellow-red) when no RGB present ----
    if (!hasRGB) {
      var minZ = Infinity, maxZ = -Infinity;
      for (var h = 0; h < vertexCount; h++) {
        var z = positions[h * 3 + 2];
        if (isFinite(z)) {
          if (z < minZ) minZ = z;
          if (z > maxZ) maxZ = z;
        }
      }
      var rangeZ = (isFinite(minZ) && maxZ > minZ) ? (maxZ - minZ) : 1;
      for (var c = 0; c < vertexCount; c++) {
        var zv = positions[c * 3 + 2];
        var t = isFinite(zv) ? (zv - minZ) / rangeZ : 0;
        var col = greenYellowRed(t);
        colors[c * 3]     = col[0];
        colors[c * 3 + 1] = col[1];
        colors[c * 3 + 2] = col[2];
      }
    }

    return { positions: positions, colors: colors, vertexCount: vertexCount };
  }

  // =========================================
  // Three.js point cloud viewer
  // =========================================
  function createViewer(containerId) {
    var container = document.getElementById(containerId);
    if (!container) return null;

    var scene = new THREE.Scene();
    scene.background = new THREE.Color(0x1a1a2e);

    var w = container.clientWidth;
    var h = container.clientHeight;
    var camera = new THREE.PerspectiveCamera(60, w / h, 0.01, 10000);
    camera.position.set(0, 0, 5);

    var renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setSize(w, h);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    container.appendChild(renderer.domElement);

    var controls = new THREE.TrackballControls(camera, renderer.domElement);
    controls.rotateSpeed = 2.0;
    controls.zoomSpeed = 1.5;
    controls.panSpeed = 1.0;
    controls.staticMoving = true;
    controls.dynamicDampingFactor = 0.3;

    var points = null;
    var savedCenter = new THREE.Vector3();
    var savedDist = 1;

    function animate() {
      requestAnimationFrame(animate);
      controls.update();
      renderer.render(scene, camera);
    }
    animate();

    window.addEventListener("resize", function () {
      var nw = container.clientWidth;
      var nh = container.clientHeight;
      camera.aspect = nw / nh;
      camera.updateProjectionMatrix();
      renderer.setSize(nw, nh);
    });

    function clear() {
      if (points) {
        scene.remove(points);
        points.geometry.dispose();
        points.material.dispose();
        points = null;
      }
    }

    function setPointCloud(positions, colorsArr) {
      clear();
      var geometry = new THREE.BufferGeometry();
      geometry.setAttribute(
        "position",
        new THREE.BufferAttribute(positions, 3)
      );
      geometry.setAttribute(
        "color",
        new THREE.BufferAttribute(colorsArr, 3)
      );

      var material = new THREE.PointsMaterial({
        size: 2.0,
        vertexColors: true,
        sizeAttenuation: false,
      });

      points = new THREE.Points(geometry, material);
      scene.add(points);

      // Compute bounding box — camera positioning happens via positionCamera()
      geometry.computeBoundingBox();
      var box = geometry.boundingBox;
      savedCenter = box.getCenter(new THREE.Vector3());
      var sz = box.getSize(new THREE.Vector3());
      var maxDim = Math.max(sz.x, sz.y, sz.z);
      var fov = camera.fov * (Math.PI / 180);
      savedDist = (maxDim / 2 / Math.tan(fov / 2)) * 1.5;
    }

    // Position camera using CloudCompare-style XYZ Euler angles (degrees).
    // Formula: camera direction from scene = R^T * [0,0,1], R = Rz*Ry*Rx.
    function positionCamera(rx, ry, rz) {
      var rxR = rx * Math.PI / 180;
      var ryR = ry * Math.PI / 180;
      var rzR = rz * Math.PI / 180;

      // Camera-from-scene direction
      var dx = -Math.sin(ryR);
      var dy =  Math.cos(ryR) * Math.sin(rxR);
      var dz =  Math.cos(ryR) * Math.cos(rxR);

      // Camera up vector
      var ux =  Math.sin(rzR) * Math.cos(ryR);
      var uy =  Math.cos(rzR) * Math.cos(rxR) + Math.sin(rzR) * Math.sin(ryR) * Math.sin(rxR);
      var uz = -Math.cos(rzR) * Math.sin(rxR) + Math.sin(rzR) * Math.sin(ryR) * Math.cos(rxR);

      camera.position.set(
        savedCenter.x + dx * savedDist,
        savedCenter.y + dy * savedDist,
        savedCenter.z + dz * savedDist
      );
      camera.up.set(ux, uy, uz);
      camera.lookAt(savedCenter);
      controls.target.copy(savedCenter);
      controls.update();
    }

    return {
      camera: camera,
      controls: controls,
      setPointCloud: setPointCloud,
      positionCamera: positionCamera,
      clear: clear,
    };
  }

  // =========================================
  // Bidirectional camera synchronization
  // =========================================
  function setupCameraSync(v1, v2) {
    var syncing = false;

    function sync(src, dst) {
      dst.camera.position.copy(src.camera.position);
      dst.camera.quaternion.copy(src.camera.quaternion);
      dst.camera.up.copy(src.camera.up);
      dst.controls.target.copy(src.controls.target);
      dst.camera.updateProjectionMatrix();
      dst.controls.update();
    }

    v1.controls.addEventListener("change", function () {
      if (syncing) return;
      syncing = true;
      sync(v1, v2);
      syncing = false;
    });

    v2.controls.addEventListener("change", function () {
      if (syncing) return;
      syncing = true;
      sync(v2, v1);
      syncing = false;
    });
  }

  // =========================================
  // Initialization
  // =========================================
  document.addEventListener("DOMContentLoaded", function () {
    var viewer0 = createViewer("viewer-epoch0");
    var viewer1 = createViewer("viewer-epoch1");
    if (!viewer0 || !viewer1) return;

    setupCameraSync(viewer0, viewer1);

    var statusEl = document.getElementById("viewer-status");

    // Scene selector buttons
    var buttons = document.querySelectorAll(".scene-btn");
    buttons.forEach(function (btn) {
      btn.addEventListener("click", function () {
        buttons.forEach(function (b) {
          b.classList.remove("active");
        });
        btn.classList.add("active");
        loadScene(btn.dataset.scene);
      });
    });

    function loadScene(sceneId) {
      if (statusEl) {
        statusEl.textContent = "Loading point clouds\u2026";
        statusEl.className = "viewer-status loading";
        statusEl.style.display = "block";
      }

      Promise.all([
        fetch(BASE_PATH + "/" + sceneId + "/0.ply").then(function (r) {
          if (!r.ok) throw new Error("0.ply not found");
          return r.arrayBuffer();
        }),
        fetch(BASE_PATH + "/" + sceneId + "/1.ply").then(function (r) {
          if (!r.ok) throw new Error("1.ply not found");
          return r.arrayBuffer();
        }),
      ])
        .then(function (buffers) {
          var pc0 = parsePLY(buffers[0]);
          var pc1 = parsePLY(buffers[1]);

          viewer0.setPointCloud(pc0.positions, pc0.colors);
          viewer1.setPointCloud(pc1.positions, pc1.colors);

          // Position camera using per-scene CloudCompare viewpoint angles
          var sceneDef = null;
          for (var si = 0; si < SCENES.length; si++) {
            if (SCENES[si].id === sceneId) { sceneDef = SCENES[si]; break; }
          }
          var rx = sceneDef ? sceneDef.rx : 45;
          var ry = sceneDef ? sceneDef.ry : 0;
          var rz = sceneDef ? sceneDef.rz : 180;
          viewer0.positionCamera(rx, ry, rz);
          // Sync viewer1 camera to viewer0
          viewer1.camera.position.copy(viewer0.camera.position);
          viewer1.camera.quaternion.copy(viewer0.camera.quaternion);
          viewer1.camera.up.copy(viewer0.camera.up);
          viewer1.controls.target.copy(viewer0.controls.target);
          viewer1.camera.updateProjectionMatrix();
          viewer1.controls.update();

          if (statusEl) statusEl.style.display = "none";
        })
        .catch(function (err) {
          if (statusEl) {
            statusEl.textContent =
              "Point cloud files not yet available for this scene. Place .ply files in assets/clouds/" +
              sceneId +
              "/";
            statusEl.className = "viewer-status error";
            statusEl.style.display = "block";
          }
          viewer0.clear();
          viewer1.clear();
        });
    }

    // Load first scene by default
    var firstBtn = document.querySelector(".scene-btn");
    if (firstBtn) {
      firstBtn.classList.add("active");
      loadScene(firstBtn.dataset.scene);
    }
  });
})();
