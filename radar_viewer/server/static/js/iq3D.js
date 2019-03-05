/*
* Copyright (c) Acconeer AB, 2018
* All rights reserved
*/

var scene, camera, renderer, controls;
initThreejsEnv();

var iqData = [];
var iqGeo = [];
var iqDot = [];
var length = 25;
var axisLength = 100;

lineMaterial = new THREE.LineBasicMaterial({
  color: 0x2888A9, linewidth: 1
});
axisLineMaterial = new THREE.LineBasicMaterial({
  color: 0x2888A9, linewidth: 2
});
dotMaterial = new THREE.PointsMaterial({
  color: 0x2888A9, size: 1
});

var textMesh = loadThreejsText(['Distance [cm]', 'Re unit [I]', 'Im unit [Q]'], function(textMesh) {
  textMesh[0].rotation.x = -Math.PI / 2;
  textMesh[0].position.z = length + 5;
  textMesh[0].position.x = -11;
  scene.add(textMesh[0]);
  textMesh[1].rotation.y = Math.PI / 2;
  textMesh[1].position.z = -(length + 6);
  scene.add(textMesh[1]);
  textMesh[2].rotation.z = Math.PI / 2;
  textMesh[2].rotation.y = Math.PI / 2;
  textMesh[2].position.y = length + 6;
  scene.add(textMesh[2]);
});

var axisGeo = new THREE.Geometry();
axisGeo.vertices.push(new THREE.Vector3((axisLength / 2), 0, 0));
axisGeo.vertices.push(new THREE.Vector3(-(axisLength / 2), 0, 0));
var axisLine = new THREE.Line(axisGeo, axisLineMaterial);
scene.add(axisLine);

var realAxisGeo = new THREE.Geometry();
realAxisGeo.vertices.push(new THREE.Vector3(0, 0, 0));
realAxisGeo.vertices.push(new THREE.Vector3(0, length + 5, 0));
var realAxisLine = new THREE.Line(realAxisGeo, axisLineMaterial);
scene.add(realAxisLine);

var imAxisGeo = new THREE.Geometry();
imAxisGeo.vertices.push(new THREE.Vector3(0, 0, 0));
imAxisGeo.vertices.push(new THREE.Vector3(0, 0, -(length + 5)));
var imAxisLine = new THREE.Line(imAxisGeo, axisLineMaterial);
scene.add(imAxisLine);

var grid = new THREE.GridHelper(axisLength, 10, 0x808080, 0xD3D3D3);
grid.position.y = -(length + 5);
scene.add(grid);

camera.position.y = 70;
camera.position.x = 90;

function makeDatapoints(nbrOfPoints) {
  var group = new THREE.Group();

  var lineDistance = axisLength / nbrOfPoints;
  for(var i = 0; i < nbrOfPoints; i++) {
    var position = (i * lineDistance) - (axisLength / 2) + (lineDistance / 2);
    iqData[i] = new THREE.Vector3(position, 0, 0);

    iqGeo[i] = new THREE.Geometry();
    iqGeo[i].vertices.push(iqData[i]);
    iqGeo[i].vertices.push(new THREE.Vector3(position, 0, 0));
    var line = new THREE.Line(iqGeo[i], lineMaterial);
    group.add(line);

    iqDot[i] = new THREE.Geometry();
    iqDot[i].vertices.push(iqData[i]);
    var dot = new THREE.Points(iqDot[i], dotMaterial);
    group.add(dot);
  }
  return group;
}

var datapoints;
var prevNbrOfPoints = 0;
getData(function(data) {
  if(data.length != prevNbrOfPoints) {
    scene.remove(datapoints);
    datapoints = makeDatapoints(data.length)
    scene.add(datapoints);
  }
  for(var i = 0; i < data.length; i++) {
    var point = data[i];
    iqData[i].setY(point['im'] * length);
    iqData[i].setZ(point['re'] * length);
    iqGeo[i].verticesNeedUpdate = true;
    iqDot[i].verticesNeedUpdate = true;
  }
}, 'iq');
