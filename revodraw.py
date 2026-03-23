#!/usr/bin/env python3
"""
RevoDraw - Card Drawing Web UI

A local web interface for drawing images on Revolut card customization screen.
Works with any Android device connected via ADB.

Usage:
    pip install flask
    python webapp.py
    Open http://localhost:5000
"""

import os
import io
import json
import base64
import subprocess
import time
import math
from pathlib import Path
from dataclasses import asdict

import argparse
import cv2
import numpy as np
from flask import Flask, render_template_string, request, jsonify, send_file

from detect_drawing_area import detect_from_screenshot, capture_screenshot, DrawingArea

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max upload

# Store state
STATE = {
    'drawing_area': None,
    'image_paths': None,
    'offset_x': 0,
    'offset_y': 0,
    'scale': 1.0,
    'drawing': False,
    'paused': False
}


HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>RevoDraw</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #1a1a2e;
            color: #eee;
            min-height: 100vh;
            padding: 20px;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
        }
        h1 {
            text-align: center;
            margin-bottom: 20px;
            color: #00d4ff;
        }
        .panels {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
        }
        @media (max-width: 900px) {
            .panels { grid-template-columns: 1fr; }
        }
        .panel {
            background: #16213e;
            border-radius: 12px;
            padding: 20px;
        }
        .panel h2 {
            margin-bottom: 15px;
            color: #00d4ff;
            font-size: 1.1em;
        }
        .btn {
            background: #0f3460;
            color: white;
            border: none;
            padding: 12px 24px;
            border-radius: 8px;
            cursor: pointer;
            font-size: 14px;
            transition: background 0.2s;
            margin: 5px;
        }
        .btn:hover { background: #1a5276; }
        .btn:disabled { opacity: 0.5; cursor: not-allowed; }
        .btn-primary { background: #00d4ff; color: #1a1a2e; }
        .btn-primary:hover { background: #00a8cc; }
        .btn-danger { background: #e74c3c; }
        .btn-danger:hover { background: #c0392b; }

        #dropZone {
            border: 2px dashed #0f3460;
            border-radius: 12px;
            padding: 40px;
            text-align: center;
            cursor: pointer;
            transition: all 0.2s;
            margin-bottom: 15px;
        }
        #dropZone:hover, #dropZone.dragover {
            border-color: #00d4ff;
            background: rgba(0, 212, 255, 0.1);
        }
        #dropZone input { display: none; }

        .preview-container {
            position: relative;
            background: #0a0a1a;
            border-radius: 8px;
            overflow: hidden;
            margin: 15px 0;
        }
        #previewCanvas {
            display: block;
            width: 100%;
            cursor: move;
        }

        .controls {
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            align-items: center;
            margin: 15px 0;
        }
        .control-group {
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .control-group label {
            font-size: 13px;
            color: #aaa;
        }
        input[type="range"] {
            width: 120px;
            accent-color: #00d4ff;
        }
        input[type="number"] {
            width: 70px;
            padding: 6px;
            border: 1px solid #0f3460;
            border-radius: 4px;
            background: #0a0a1a;
            color: white;
        }
        select {
            padding: 8px 12px;
            border: 1px solid #0f3460;
            border-radius: 4px;
            background: #0a0a1a;
            color: white;
        }

        .status {
            padding: 12px;
            border-radius: 8px;
            margin: 10px 0;
            font-size: 13px;
        }
        .status.info { background: rgba(0, 212, 255, 0.2); }
        .status.success { background: rgba(46, 204, 113, 0.2); }
        .status.error { background: rgba(231, 76, 60, 0.2); }
        .status.warning { background: rgba(241, 196, 15, 0.2); }

        .progress-bar {
            height: 4px;
            background: #0f3460;
            border-radius: 2px;
            overflow: hidden;
            margin: 10px 0;
        }
        .progress-bar-fill {
            height: 100%;
            background: #00d4ff;
            width: 0%;
            transition: width 0.3s;
        }

        /* Range Selector Styles */
        .range-container {
            position: relative;
            height: 40px;
            background: #0a0a1a;
            border-radius: 8px;
            margin: 10px 0;
            padding: 0 10px;
            display: flex;
            align-items: center;
            user-select: none;
        }
        .range-track {
            position: relative;
            width: 100%;
            height: 6px;
            background: #0f3460;
            border-radius: 3px;
        }
        .range-fill {
            position: absolute;
            height: 100%;
            background: #00d4ff;
            border-radius: 3px;
            opacity: 0.3;
        }
        .range-handle {
            position: absolute;
            width: 20px;
            height: 20px;
            background: #00d4ff;
            border-radius: 50%;
            top: 50%;
            transform: translate(-50%, -50%);
            cursor: pointer;
            box-shadow: 0 0 10px rgba(0, 212, 255, 0.5);
            z-index: 2;
        }
        .range-handle::after {
            content: '';
            position: absolute;
            width: 8px;
            height: 8px;
            background: #1a1a2e;
            border-radius: 50%;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
        }
        .range-handle:active {
            transform: translate(-50%, -50%) scale(1.2);
        }
        .range-info span { font-family: monospace; }
        
        .range-ticks {
            position: absolute;
            width: 100%;
            display: flex;
            justify-content: space-between;
            bottom: -5px;
            pointer-events: none;
            padding: 0 10px;
            box-sizing: border-box;
        }
        .range-tick {
            width: 1px;
            height: 5px;
            background: #0f3460;
            position: relative;
        }
        .range-tick::after {
            content: attr(data-label);
            position: absolute;
            top: 6px;
            left: 50%;
            transform: translateX(-50%);
            font-size: 8px;
            color: #555;
        }
        .range-tick.major { height: 8px; background: #34495e; }
        .range-tick.major::after { color: #888; }
        
        /* Points Editor Styles */
        .points-editor {
            margin-top: 15px;
            background: rgba(0,0,0,0.2);
            border-radius: 8px;
            padding: 10px;
            border: 1px solid rgba(255,255,255,0.05);
            max-height: 400px;
            display: flex;
            flex-direction: column;
        }
        .points-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 8px;
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 1px;
            color: #666;
        }
        .pt-btn-del:hover { color: #ff0000; }
        
        .points-grid-container {
            overflow-y: auto;
            flex-grow: 1;
            max-height: 400px;
        }
        .points-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(130px, 1fr));
            gap: 2px;
            padding: 5px;
        }
        .pt-item {
            display: flex;
            align-items: center;
            background: rgba(255,255,255,0.03);
            border-radius: 4px;
            padding: 1px 4px;
            font-size: 10px;
            gap: 2px;
        }
        .pt-item span.idx { color: #444; width: 25px; text-align: right; margin-right: 4px; }
        .pt-item .coord { display: flex; align-items: center; color: #666; }
        .pt-item input {
            background: transparent;
            border: none;
            color: #00d4ff;
            width: 35px;
            font-family: monospace;
            padding: 1px;
            text-align: center;
        }
        .pt-item input:focus { color: #fff; background: rgba(0,212,255,0.2); border-radius: 2px; }
        
        /* Hide number input spinners ONLY for points editor */
        .pt-item input::-webkit-outer-spin-button,
        .pt-item input::-webkit-inner-spin-button { -webkit-appearance: none; margin: 0; }
        .pt-item input[type=number] { -moz-appearance: textfield; }

        .editor-actions {
            display: flex;
            gap: 8px;
            margin-top: 10px;
            padding-top: 10px;
            border-top: 1px solid rgba(255,255,255,0.1);
        }

        #log {
            background: #0a0a1a;
            border-radius: 8px;
            padding: 15px;
            font-family: monospace;
            font-size: 12px;
            max-height: 200px;
            overflow-y: auto;
            white-space: pre-wrap;
        }

        .stats {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 10px;
            margin: 15px 0;
        }
        .stat {
            background: #0a0a1a;
            padding: 10px;
            border-radius: 6px;
            text-align: center;
        }
        .stat-value {
            font-size: 1.5em;
            color: #00d4ff;
        }
        .stat-label {
            font-size: 11px;
            color: #888;
        }
        .layer-item {
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 8px 12px;
            background: #0a0a1a;
            border-radius: 6px;
            margin: 4px 0;
            cursor: pointer;
            border: 2px solid transparent;
        }
        .layer-item.active {
            border-color: #00d4ff;
        }
        .layer-item:hover {
            background: #1a1a3a;
        }
        .layer-name {
            flex: 1;
            font-size: 13px;
        }
        .layer-info {
            font-size: 11px;
            color: #888;
        }
        .layer-delete {
            background: none;
            border: none;
            color: #e74c3c;
            font-size: 18px;
            cursor: pointer;
            padding: 0 4px;
        }
        .tool-btn.active {
            background: #00d4ff;
            color: #1a1a2e;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🎨 RevoDraw</h1>

        <div class="panels">
            <div class="panel">
                <h2>1. Upload Images</h2>
                <div id="dropZone">
                    <input type="file" id="imageInput" accept="image/*">
                    <p>📁 Drop image here or click to upload</p>
                </div>
                <div id="layerList" style="margin-top:10px;"></div>
                <button class="btn" id="addLayerBtn" style="display:none;" onclick="document.getElementById('imageInput').click()">+ Add Another Image</button>

                <h2>2. Edge Detection</h2>
                <div class="controls">
                    <div class="control-group">
                        <label>Method:</label>
                        <select id="method">
                            <option value="auto">Auto</option>
                            <option value="edges">Edges (photos)</option>
                            <option value="contours">Contours (logos)</option>
                            <option value="contours_inv">Contours Inverted</option>
                            <option value="adaptive">Adaptive</option>
                        </select>
                    </div>
                    <div class="control-group">
                        <label>Threshold:</label>
                        <input type="range" id="threshold" min="0" max="255" value="127">
                        <span id="thresholdVal">127</span>
                    </div>
                    <div class="control-group">
                        <label>Simplify:</label>
                        <input type="range" id="simplify" min="0" max="10" step="0.5" value="2">
                        <span id="simplifyVal">2</span>
                    </div>
                    <div class="control-group" style="display:flex; align-items:center; gap:10px;">
                        <label>Fill:</label>
                        <input type="checkbox" id="fillShape">
                        <label title="Space between fill lines">Spacing:</label>
                        <input type="number" id="fillSpacing" min="1" max="20" value="4" style="width:50px;">
                    </div>
                </div>
                <button class="btn" onclick="processImage()">🔄 Process Image</button>
                <button class="btn" id="reprocessBtn" onclick="reprocessLayer()" style="display:none;">🔄 Reprocess Selected</button>

                <div class="stats" id="stats" style="display:none;">
                    <div class="stat">
                        <div class="stat-value" id="pathCount">0</div>
                        <div class="stat-label">Paths</div>
                    </div>
                    <div class="stat">
                        <div class="stat-value" id="pointCount">0</div>
                        <div class="stat-label">Points</div>
                    </div>
                    <div class="stat">
                        <div class="stat-value" id="estTime">0s</div>
                        <div class="stat-label">Est. Time</div>
                    </div>
                </div>
                <div id="edgePreview" style="display:none; margin-top:15px;">
                    <canvas id="edgeCanvas" width="300" height="300" style="background:#000; border-radius:8px; width:100%; max-width:300px;"></canvas>
                </div>
            </div>

            <div class="panel">
                <h2>3. Position & Preview</h2>
                <div class="preview-container">
                    <canvas id="previewCanvas" width="540" height="600"></canvas>
                </div>

                <div class="controls" style="margin-bottom:10px;">
                    <div class="control-group">
                        <label>Tool:</label>
                        <button class="btn tool-btn active" id="toolMove" onclick="setTool('move')">✋ Move</button>
                        <button class="btn tool-btn" id="toolErase" onclick="setTool('erase')">🧹 Eraser</button>
                    </div>
                    <div class="control-group" id="eraserSizeGroup" style="display:none;">
                        <label>Size:</label>
                        <input type="range" id="eraserSize" min="10" max="100" value="30">
                        <span id="eraserSizeVal">30</span>
                    </div>
                </div>

                <div class="controls" style="margin-bottom:10px;">
                    <div class="control-group">
                        <label>Scale X:</label>
                        <input type="range" id="scaleX" min="0.1" max="5" step="0.05" value="1">
                        <span id="scaleXVal">100%</span>
                    </div>
                    <div class="control-group">
                        <label>Scale Y:</label>
                        <input type="range" id="scaleY" min="0.1" max="5" step="0.05" value="1">
                        <span id="scaleYVal">100%</span>
                    </div>
                    <div class="control-group">
                        <label>🔗</label>
                        <input type="checkbox" id="lockAspect" checked>
                    </div>
                </div>

                <div class="controls" style="margin-bottom:10px;">
                    <div class="control-group">
                        <label>Rotate:</label>
                        <input type="range" id="rotation" min="-180" max="180" step="5" value="0">
                        <span id="rotationVal">0°</span>
                    </div>
                    <button class="btn" onclick="rotate90(-1)">↶ 90</button>
                    <button class="btn" onclick="rotate90(1)">↷ 90</button>
                </div>

                <div class="controls">
                    <button class="btn" onclick="flipH()">↔ Flip H</button>
                    <button class="btn" onclick="flipV()">↕ Flip V</button>
                    <button class="btn" onclick="resetPosition()">↺ Reset</button>
                    <button class="btn" onclick="undoErase()">⟲ Undo</button>
                    <button class="btn" onclick="detectArea()">📱 Detect Area</button>
                    <input type="file" id="screenshotInput" accept="image/*" style="display:none"
                        onchange="detectAreaFromFile(this.files[0])">
                    <button class="btn" onclick="document.getElementById('screenshotInput').click()">📂 Load Screenshot</button>
                </div>
                <div id="areaStatus" class="status info">Click "Detect Area" to capture phone screen, or load a screenshot manually</div>
            </div>
        </div>

        <div class="panel" style="margin-top: 20px;">
            <h2>4. Draw on Phone</h2>
            <div class="controls" style="flex-wrap:wrap; gap:8px;">
                <button class="btn btn-primary" id="drawBtn" onclick="startDrawingRange()" disabled>
                    ✏️ Start Drawing
                </button>
                <button class="btn btn-danger" id="stopBtn" onclick="stopDrawing()" disabled>
                    ⏹ Stop
                </button>
                <button class="btn" id="pauseBtn" onclick="togglePause()" disabled style="background:#e67e22;">
                    ⏸ Pause
                </button>
                <div class="control-group" style="margin-left:10px;">
                    <label>Stroke:</label>
                    <input type="range" id="strokeDuration" min="20" max="150" value="60">
                    <span id="strokeVal">60ms</span>
                </div>
                <div class="control-group">
                    <label>Delay:</label>
                    <input type="range" id="strokeDelay" min="5" max="50" value="15">
                    <span id="delayVal">15ms</span>
                </div>
                <div class="control-group" style="margin-left:6px;">
                    <span id="timeEstLabel" style="font-size:10px; color:#888;">⏱ --</span>
                </div>
            </div>

            <!-- Range Selector, shown when total points > 0 -->
            <div id="partsPanel" style="display:none; margin-top:15px; padding:15px; background:rgba(255,255,255,0.05); border-radius:12px;">
                <div class="range-info">
                    <span id="rangeStartLabel">Start: 0%</span>
                    <span id="rangePointsLabel" style="color:#00d4ff; font-weight:bold;">Selection: 0 pts</span>
                    <span id="rangeEndLabel">End: 100%</span>
                </div>
                <div class="range-container" id="rangeContainer">
                    <div style="position:relative; width:100%; height:100%; display:flex; align-items:center;">
                        <div class="range-track">
                            <div class="range-fill" id="rangeFill" style="left:0%; width:100%;"></div>
                        </div>
                        <div class="range-handle" id="handleStart" style="left: 0%;"></div>
                        <div class="range-handle" id="handleEnd" style="left: 100%;"></div>
                        <div class="range-ticks" style="padding:0;"> <!-- Removed padding since parent handles it -->
                            <div class="range-tick major" data-label="0%"></div>
                        <div class="range-tick" data-label=""></div>
                        <div class="range-tick" data-label=""></div>
                        <div class="range-tick" data-label=""></div>
                        <div class="range-tick" data-label=""></div>
                        <div class="range-tick major" data-label="25%"></div>
                        <div class="range-tick" data-label=""></div>
                        <div class="range-tick" data-label=""></div>
                        <div class="range-tick" data-label=""></div>
                        <div class="range-tick" data-label=""></div>
                        <div class="range-tick major" data-label="50%"></div>
                        <div class="range-tick" data-label=""></div>
                        <div class="range-tick" data-label=""></div>
                        <div class="range-tick" data-label=""></div>
                        <div class="range-tick" data-label=""></div>
                        <div class="range-tick major" data-label="75%"></div>
                        <div class="range-tick" data-label=""></div>
                        <div class="range-tick" data-label=""></div>
                        <div class="range-tick" data-label=""></div>
                        <div class="range-tick" data-label=""></div>
                        <div class="range-tick major" data-label="100%"></div>
                        </div>
                    </div>
                </div>
                <div class="controls" style="margin-top:20px; justify-content: space-between; flex-wrap:nowrap;">
                    <div class="control-group" style="gap:6px;">
                        <button class="btn btn-primary" id="playSelBtn" onclick="startDrawingRange()" style="padding:6px 12px; font-size:12px;">
                            ▶ Play Selection
                        </button>
                        <button class="btn" id="playNextBtn" onclick="playNext()" style="padding:6px 12px; font-size:12px; opacity:0.8;">
                            ⏭ Play Next
                        </button>
                        <label style="cursor:pointer; display:flex; align-items:center; gap:5px; font-size:11px;" title="Automatically play the next segment when finished">
                            <input type="checkbox" id="autoPlay">
                            <span>Auto Play</span>
                        </label>
                        <button class="btn" onclick="resetRange()" style="padding:4px 12px; font-size:11px; margin-left:10px;">
                            🔄 Reset
                        </button>
                    </div>
                    <div class="control-group" style="gap:10px;">
                        <label style="cursor:pointer; display:flex; align-items:center; gap:5px;">
                            <input type="checkbox" id="tryMode">
                            <span title="Draw a rough sketch before the full selection">Try Mode</span>
                        </label>
                    </div>
                </div>
                <!-- Preconfigured Parts -->
                <!-- Split Parts -->
                <div style="margin-top:10px; border-top:1px solid rgba(255,255,255,0.05); padding-top:10px;">
                    <div class="controls" style="gap:10px; align-items:center;">
                        <label style="font-size:11px; color:#666;">Split Parts:</label>
                        <input type="number" id="splitPartsCount" value="4" min="1" max="20" style="width:40px; padding:2px 4px; font-size:11px;" onchange="updateSplitParts()">
                        <div id="splitPartsContainer" style="display:flex; flex-wrap:wrap; gap:4px;"></div>
                    </div>
                </div>

                <!-- Points Editor (Initially Hidden) -->
                <div id="pointsEditor" style="display:none;" class="points-editor">
                    <div class="points-header">
                        <span>Points Editor</span>
                        <button class="btn" onclick="togglePointsEditor()" style="padding:2px 8px; font-size:10px;">Close</button>
                    </div>
                    <div class="points-grid-container">
                        <div class="points-grid" id="pointsGrid"></div>
                    </div>
                    <div id="editorStats" style="font-size:10px; color:#555; margin-top:5px; text-align:center;"></div>
                    <div class="editor-actions">
                        <button class="btn" style="padding:4px 8px; font-size:10px;" onclick="bulkThinSelection()">Thin (Remove 50%)</button>
                        <button class="btn" style="padding:4px 8px; font-size:10px;" onclick="bulkDeleteSelection()">Delete All Selected</button>
                        <button class="btn btn-primary" style="padding:4px 8px; font-size:10px; margin-left:auto;" onclick="applyPointEdits()">Save Edits</button>
                    </div>
                </div>
                <div style="text-align:center; margin-top:10px;">
                    <button id="showEditorBtn" class="btn" style="padding:4px 12px; font-size:11px; background:rgba(255,255,255,0.05);" onclick="togglePointsEditor()">
                        🔍 View/Edit Selected Points
                    </button>
                </div>
            </div>

            <div class="progress-bar" style="margin-top:10px;">
                <div class="progress-bar-fill" id="progressBar"></div>
            </div>
            <div id="drawStatus" class="status info">Upload an image and detect area to begin</div>
            <div id="log"></div>
        </div>
    </div>

    <script>
        const sleep = ms => new Promise(res => setTimeout(res, ms));

        let originalImage = null;
        let processedPaths = null;
        let pathsHistory = [];  // For undo
        let drawingArea = null;
        let isDragging = false;
        let dragStart = {x: 0, y: 0};
        let imageOffset = {x: 0, y: 0};
        let scaleX = 1.0, scaleY = 1.0;
        let rotation = 0;
        let flipHorizontal = false, flipVertical = false;
        let isDrawing = false;
        let currentTool = 'move';
        let eraserSize = 30;
        let mousePos = {x: 0, y: 0};
        
        // Range selection state
        let rangeStartPct = 0;
        let rangeEndPct = 100;
        let activeHandle = null;
        let pointSelectionMapping = []; // [{lIdx, pIdx, ptIdx}]

        // Multi-layer support
        let layers = [];  // {name, paths, offset, scaleX, scaleY, rotation, flipH, flipV, visible}
        let activeLayerIndex = -1;

        const canvas = document.getElementById('previewCanvas');
        const ctx = canvas.getContext('2d');

        // File upload handling
        const dropZone = document.getElementById('dropZone');
        const imageInput = document.getElementById('imageInput');

        dropZone.onclick = () => imageInput.click();
        dropZone.ondragover = (e) => { e.preventDefault(); dropZone.classList.add('dragover'); };
        dropZone.ondragleave = () => dropZone.classList.remove('dragover');
        dropZone.ondrop = (e) => {
            e.preventDefault();
            dropZone.classList.remove('dragover');
            if (e.dataTransfer.files.length) handleFile(e.dataTransfer.files[0]);
        };
        imageInput.onchange = () => { if (imageInput.files.length) handleFile(imageInput.files[0]); };

        let currentFileName = '';

        function handleFile(file) {
            if (!file.type.startsWith('image/')) {
                alert('Please upload an image file');
                return;
            }
            currentFileName = file.name;
            const reader = new FileReader();
            reader.onload = (e) => {
                // Resize image before storing to avoid 413 errors
                const img = new Image();
                img.onload = () => {
                    const maxSize = 500;  // Reduced for smaller payload
                    let w = img.width, h = img.height;
                    if (Math.max(w, h) > maxSize) {
                        const scale = maxSize / Math.max(w, h);
                        w = Math.round(w * scale);
                        h = Math.round(h * scale);
                    }
                    const tempCanvas = document.createElement('canvas');
                    tempCanvas.width = w;
                    tempCanvas.height = h;
                    const tempCtx = tempCanvas.getContext('2d');
                    tempCtx.drawImage(img, 0, 0, w, h);
                    // Use JPEG for much smaller file size
                    originalImage = tempCanvas.toDataURL('image/jpeg', 0.8);
                    dropZone.innerHTML = `<p>✅ ${file.name} (${w}x${h})</p><p style="font-size:11px;color:#888;">Click "Process Image" to add</p>`;
                    log('Image loaded: ' + file.name + ' (' + w + 'x' + h + ')');
                };
                img.src = e.target.result;
            };
            reader.readAsDataURL(file);
        }

        // Sliders
        document.getElementById('threshold').oninput = (e) => {
            document.getElementById('thresholdVal').textContent = e.target.value;
        };
        document.getElementById('simplify').oninput = (e) => {
            document.getElementById('simplifyVal').textContent = e.target.value;
        };
        document.getElementById('scaleX').oninput = (e) => {
            scaleX = parseFloat(e.target.value);
            document.getElementById('scaleXVal').textContent = Math.round(scaleX * 100) + '%';
            if (document.getElementById('lockAspect').checked) {
                scaleY = scaleX;
                document.getElementById('scaleY').value = scaleX;
                document.getElementById('scaleYVal').textContent = Math.round(scaleY * 100) + '%';
            }
            updatePreview();
        };
        document.getElementById('scaleY').oninput = (e) => {
            scaleY = parseFloat(e.target.value);
            document.getElementById('scaleYVal').textContent = Math.round(scaleY * 100) + '%';
            if (document.getElementById('lockAspect').checked) {
                scaleX = scaleY;
                document.getElementById('scaleX').value = scaleY;
                document.getElementById('scaleXVal').textContent = Math.round(scaleX * 100) + '%';
            }
            updatePreview();
        };
        document.getElementById('rotation').oninput = (e) => {
            rotation = parseInt(e.target.value);
            document.getElementById('rotationVal').textContent = rotation + '°';
            updatePreview();
        };
        document.getElementById('eraserSize').oninput = (e) => {
            eraserSize = parseInt(e.target.value);
            document.getElementById('eraserSizeVal').textContent = eraserSize;
        };
        document.getElementById('strokeDuration').oninput = (e) => {
            document.getElementById('strokeVal').textContent = e.target.value + 'ms';
            updateTimeEstimate();
        };
        document.getElementById('strokeDelay').oninput = (e) => {
            document.getElementById('delayVal').textContent = e.target.value + 'ms';
            updateTimeEstimate();
        };

        function updateTimeEstimate() {
            const strokeMs = parseInt(document.getElementById('strokeDuration').value);
            const delayMs  = parseInt(document.getElementById('strokeDelay').value);
            const allVisible = layers.filter(l => l.visible && l.paths && l.paths.length > 0);
            const totalPaths = allVisible.reduce((s, l) => s + l.paths.length, 0);
            if (totalPaths === 0) {
                document.getElementById('timeEstLabel').textContent = '⏱ --';
                return;
            }
            // Count paths in range roughly (use sliceLayersForRange path count)
            const selPaths  = sliceLayersForRange(rangeStartPct, rangeEndPct).reduce((s,l)=>s+l.paths.length,0);
            const totalMs = selPaths * (strokeMs + delayMs);
            const secs = Math.round(totalMs / 1000);
            const label = secs >= 60 ? `⏱ ~${Math.floor(secs/60)}m ${secs%60}s` : `⏱ ~${secs}s`;
            document.getElementById('timeEstLabel').textContent = label;
        }

        function setTool(tool) {
            currentTool = tool;
            document.querySelectorAll('.tool-btn').forEach(b => b.classList.remove('active'));
            document.getElementById('tool' + tool.charAt(0).toUpperCase() + tool.slice(1)).classList.add('active');
            document.getElementById('eraserSizeGroup').style.display = tool === 'erase' ? 'flex' : 'none';
            canvas.style.cursor = tool === 'erase' ? 'crosshair' : 'move';
        }

        function rotate90(dir) {
            rotation = (rotation + dir * 90) % 360;
            document.getElementById('rotation').value = rotation;
            document.getElementById('rotationVal').textContent = rotation + '°';
            updatePreview();
        }

        function flipH() {
            flipHorizontal = !flipHorizontal;
            updatePreview();
        }

        function flipV() {
            flipVertical = !flipVertical;
            updatePreview();
        }

        function undoErase() {
            if (pathsHistory.length > 0) {
                processedPaths = pathsHistory.pop();
                if (activeLayerIndex >= 0) {
                    layers[activeLayerIndex].paths = processedPaths;
                }
                updatePreview();
                log('Undo: restored ' + processedPaths.length + ' paths');
            }
        }

        function saveCurrentLayerState() {
            if (activeLayerIndex >= 0 && layers[activeLayerIndex]) {
                // Deep copy paths to avoid reference issues
                layers[activeLayerIndex].paths = JSON.parse(JSON.stringify(processedPaths || []));
                layers[activeLayerIndex].offset = {...imageOffset};
                layers[activeLayerIndex].scaleX = scaleX;
                layers[activeLayerIndex].scaleY = scaleY;
                layers[activeLayerIndex].rotation = rotation;
                layers[activeLayerIndex].flipH = flipHorizontal;
                layers[activeLayerIndex].flipV = flipVertical;
            }
        }

        function loadLayerState(index) {
            if (index >= 0 && layers[index]) {
                const layer = layers[index];
                // Deep copy paths to avoid reference issues
                processedPaths = JSON.parse(JSON.stringify(layer.paths || []));
                imageOffset = {...layer.offset};
                scaleX = layer.scaleX;
                scaleY = layer.scaleY;
                rotation = layer.rotation;
                flipHorizontal = layer.flipH;
                flipVertical = layer.flipV;

                // Update UI
                document.getElementById('scaleX').value = scaleX;
                document.getElementById('scaleY').value = scaleY;
                document.getElementById('scaleXVal').textContent = Math.round(scaleX * 100) + '%';
                document.getElementById('scaleYVal').textContent = Math.round(scaleY * 100) + '%';
                document.getElementById('rotation').value = rotation;
                document.getElementById('rotationVal').textContent = rotation + '°';
            }
        }

        function selectLayer(index) {
            saveCurrentLayerState();
            activeLayerIndex = index;
            loadLayerState(index);
            updateLayerList();
            updatePreview();
            updateReprocessButton();
            updatePartsPanel();
        }

        function deleteLayer(index) {
            layers.splice(index, 1);
            if (activeLayerIndex >= layers.length) {
                activeLayerIndex = layers.length - 1;
            }
            if (activeLayerIndex >= 0) {
                loadLayerState(activeLayerIndex);
            } else {
                processedPaths = null;
            }
            updateLayerList();
            updatePreview();
            updateDrawButton();
            updateReprocessButton();
            updatePartsPanel();
        }

        function toggleLayerVisibility(index) {
            layers[index].visible = !layers[index].visible;
            updateLayerList();
            updatePreview();
            updatePartsPanel();
        }

        function updateLayerList() {
            const list = document.getElementById('layerList');
            if (layers.length === 0) {
                list.innerHTML = '';
                document.getElementById('addLayerBtn').style.display = 'none';
                return;
            }

            document.getElementById('addLayerBtn').style.display = 'inline-block';

            list.innerHTML = layers.map((layer, i) => `
                <div class="layer-item ${i === activeLayerIndex ? 'active' : ''}" onclick="selectLayer(${i})">
                    <input type="checkbox" ${layer.visible ? 'checked' : ''} onclick="event.stopPropagation(); toggleLayerVisibility(${i})">
                    <span class="layer-name">${layer.name}</span>
                    <span class="layer-info">${layer.paths.length} paths</span>
                    <button class="layer-delete" onclick="event.stopPropagation(); deleteLayer(${i})">×</button>
                </div>
            `).join('');
        }

        function addLayer(name, paths, imageData = null) {
            saveCurrentLayerState();
            // Deep copy paths to avoid reference issues
            const pathsCopy = JSON.parse(JSON.stringify(paths || []));
            
            // Calculate original bounding box for consistent positioning in parts
            let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
            for (const path of pathsCopy) {
                for (const [x, y] of path) {
                    minX = Math.min(minX, x);
                    minY = Math.min(minY, y);
                    maxX = Math.max(maxX, x);
                    maxY = Math.max(maxY, y);
                }
            }
            const bounds = (minX === Infinity) ? null : {minX, minY, maxX, maxY};

            layers.push({
                name: name,
                paths: pathsCopy,
                originalBounds: bounds,
                imageData: imageData,  // Store original image for reprocessing
                offset: {x: 0, y: 0},
                scaleX: 1.0,
                scaleY: 1.0,
                rotation: 0,
                flipH: false,
                flipV: false,
                visible: true
            });
            activeLayerIndex = layers.length - 1;
            loadLayerState(activeLayerIndex);
            updateLayerList();
            updateDrawButton();
            updateReprocessButton();
            updatePartsPanel();
        }

        function updateReprocessButton() {
            const btn = document.getElementById('reprocessBtn');
            if (activeLayerIndex >= 0 && layers[activeLayerIndex] && layers[activeLayerIndex].imageData) {
                btn.style.display = 'inline-block';
            } else {
                btn.style.display = 'none';
            }
        }

        async function reprocessLayer() {
            if (activeLayerIndex < 0 || !layers[activeLayerIndex] || !layers[activeLayerIndex].imageData) {
                alert('No layer selected or layer has no image data');
                return;
            }

            const layer = layers[activeLayerIndex];
            log('Reprocessing layer: ' + layer.name);

            // Convert data URL to Blob
            const base64 = layer.imageData.split(',')[1];
            const binary = atob(base64);
            const array = new Uint8Array(binary.length);
            for (let i = 0; i < binary.length; i++) {
                array[i] = binary.charCodeAt(i);
            }
            const blob = new Blob([array], {type: 'image/jpeg'});

            const formData = new FormData();
            formData.append('image', blob, 'image.jpg');
            formData.append('method', document.getElementById('method').value);
            formData.append('threshold', document.getElementById('threshold').value);
            formData.append('simplify', document.getElementById('simplify').value);
            formData.append('fill', document.getElementById('fillShape').checked ? '1' : '0');
            formData.append('spacing', document.getElementById('fillSpacing').value);

            try {
                const resp = await fetch('/process', { method: 'POST', body: formData });
                const data = await resp.json();

                if (data.error) {
                    log('Error: ' + data.error);
                    return;
                }

                // Update current layer with new paths (keep transforms)
                layer.paths = JSON.parse(JSON.stringify(data.paths));
                processedPaths = JSON.parse(JSON.stringify(data.paths));

                // Update original bounds
                let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
                for (const path of layer.paths) {
                    for (const [x, y] of path) {
                        minX = Math.min(minX, x);
                        minY = Math.min(minY, y);
                        maxX = Math.max(maxX, x);
                        maxY = Math.max(maxY, y);
                    }
                }
                layer.originalBounds = (minX === Infinity) ? null : {minX, minY, maxX, maxY};

                document.getElementById('stats').style.display = 'grid';
                document.getElementById('pathCount').textContent = data.path_count;
                document.getElementById('pointCount').textContent = data.point_count;
                document.getElementById('estTime').textContent = Math.round(data.est_time) + 's';

                drawEdgePreview(data.paths, data.width, data.height);
                updateLayerList();
                updatePreview();
                updatePartsPanel();

                log(`Reprocessed: ${data.path_count} paths, ${data.point_count} points`);
            } catch (err) {
                log('Error: ' + err.message);
            }
        }

        // Canvas event handling
        canvas.onmousedown = (e) => {
            const rect = canvas.getBoundingClientRect();
            const x = e.clientX - rect.left;
            const y = e.clientY - rect.top;

            if (currentTool === 'move') {
                isDragging = true;
                dragStart = { x: x - imageOffset.x, y: y - imageOffset.y };
            } else if (currentTool === 'erase') {
                isDragging = true;
                eraseAt(x, y);
            }
        };
        canvas.onmousemove = (e) => {
            const rect = canvas.getBoundingClientRect();
            const x = e.clientX - rect.left;
            const y = e.clientY - rect.top;
            mousePos = {x, y};

            // Always update preview to show eraser cursor
            if (currentTool === 'erase') {
                updatePreview();
            }

            if (!isDragging) return;

            if (currentTool === 'move') {
                imageOffset.x = x - dragStart.x;
                imageOffset.y = y - dragStart.y;
                updatePreview();
            } else if (currentTool === 'erase') {
                eraseAt(x, y);
            }
        };
        canvas.onmouseup = () => isDragging = false;
        canvas.onmouseleave = () => {
            isDragging = false;
            mousePos = {x: -100, y: -100};
            if (currentTool === 'erase') updatePreview();
        };

        // Touch support
        canvas.ontouchstart = (e) => {
            e.preventDefault();
            const touch = e.touches[0];
            const rect = canvas.getBoundingClientRect();
            const x = touch.clientX - rect.left;
            const y = touch.clientY - rect.top;

            if (currentTool === 'move') {
                isDragging = true;
                dragStart = { x: x - imageOffset.x, y: y - imageOffset.y };
            } else if (currentTool === 'erase') {
                isDragging = true;
                eraseAt(x, y);
            }
        };
        canvas.ontouchmove = (e) => {
            if (!isDragging) return;
            e.preventDefault();
            const touch = e.touches[0];
            const rect = canvas.getBoundingClientRect();
            const x = touch.clientX - rect.left;
            const y = touch.clientY - rect.top;

            if (currentTool === 'move') {
                imageOffset.x = x - dragStart.x;
                imageOffset.y = y - dragStart.y;
                updatePreview();
            } else if (currentTool === 'erase') {
                eraseAt(x, y);
            }
        };
        canvas.ontouchend = () => isDragging = false;

        function eraseAt(canvasX, canvasY) {
            if (activeLayerIndex < 0 || !layers[activeLayerIndex] || !drawingArea) return;

            const layer = layers[activeLayerIndex];
            if (!layer.paths || layer.paths.length === 0) return;

            // Save state for undo (only on first erase of a drag)
            if (pathsHistory.length === 0 ||
                JSON.stringify(pathsHistory[pathsHistory.length-1]) !== JSON.stringify(layer.paths)) {
                pathsHistory.push(JSON.parse(JSON.stringify(layer.paths)));
                if (pathsHistory.length > 20) pathsHistory.shift();
            }

            const eraseRadius = eraserSize;
            const area = drawingArea;

            // Calculate preview transform (same as in updatePreview)
            const previewScale = Math.min(
                canvas.width / (area.right - area.left + 100),
                canvas.height / (area.bottom - area.top + 100)
            ) * 0.9;
            const offsetX = (canvas.width - (area.right - area.left) * previewScale) / 2;
            const offsetY = (canvas.height - (area.bottom - area.top) * previewScale) / 2;
            const tx = (x) => offsetX + (x - area.left) * previewScale;
            const ty = (y) => offsetY + (y - area.top) * previewScale;

            // Calculate path bounds
            let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
            for (const path of layer.paths) {
                for (const [x, y] of path) {
                    minX = Math.min(minX, x);
                    minY = Math.min(minY, y);
                    maxX = Math.max(maxX, x);
                    maxY = Math.max(maxY, y);
                }
            }
            const pathW = maxX - minX || 1;
            const pathH = maxY - minY || 1;
            const pathCenterX = minX + pathW / 2;
            const pathCenterY = minY + pathH / 2;

            // Available area
            const availLeft = Math.max(area.left, area.top_excl_right);
            const availTop = Math.max(area.top, area.top_excl_bottom);
            const availRight = area.cutout_left;
            const availBottom = area.bottom;
            const availW = availRight - availLeft - 40;
            const availH = availBottom - availTop - 40;
            const areaCenterX = availLeft + 20 + availW / 2;
            const areaCenterY = availTop + 20 + availH / 2;
            const baseScale = Math.min(availW / pathW, availH / pathH);

            // Transform function (same as preview)
            function transformToCanvas(px, py) {
                let x = px - pathCenterX;
                let y = py - pathCenterY;
                if (flipHorizontal) x = -x;
                if (flipVertical) y = -y;
                if (rotation !== 0) {
                    const rad = rotation * Math.PI / 180;
                    const cos = Math.cos(rad), sin = Math.sin(rad);
                    const rx = x * cos - y * sin;
                    const ry = x * sin + y * cos;
                    x = rx; y = ry;
                }
                x *= baseScale * scaleX;
                y *= baseScale * scaleY;
                x += areaCenterX;
                y += areaCenterY;
                // Convert to canvas coords
                return [tx(x) + imageOffset.x, ty(y) + imageOffset.y];
            }

            // Filter out points near the eraser (remove individual points, not whole paths)
            layer.paths = layer.paths.map(path => {
                return path.filter(([px, py]) => {
                    const [cx, cy] = transformToCanvas(px, py);
                    const dist = Math.sqrt((cx - canvasX)**2 + (cy - canvasY)**2);
                    return dist > eraseRadius;
                });
            }).filter(path => path.length >= 2);

            processedPaths = JSON.parse(JSON.stringify(layer.paths));
            updateLayerList();
            updatePreview();
        }

        function resetPosition() {
            imageOffset = {x: 0, y: 0};
            scaleX = scaleY = 1.0;
            rotation = 0;
            flipHorizontal = flipVertical = false;
            document.getElementById('scaleX').value = 1;
            document.getElementById('scaleY').value = 1;
            document.getElementById('scaleXVal').textContent = '100%';
            document.getElementById('scaleYVal').textContent = '100%';
            document.getElementById('rotation').value = 0;
            document.getElementById('rotationVal').textContent = '0°';
            updatePreview();
        }

        async function processImage() {
            if (!originalImage) {
                alert('Please upload an image first');
                return;
            }

            log('Processing image...');

            // Convert data URL to Blob for proper file upload
            const base64 = originalImage.split(',')[1];
            const binary = atob(base64);
            const array = new Uint8Array(binary.length);
            for (let i = 0; i < binary.length; i++) {
                array[i] = binary.charCodeAt(i);
            }
            const blob = new Blob([array], {type: 'image/jpeg'});

            const formData = new FormData();
            formData.append('image', blob, 'image.jpg');
            formData.append('method', document.getElementById('method').value);
            formData.append('threshold', document.getElementById('threshold').value);
            formData.append('simplify', document.getElementById('simplify').value);
            formData.append('fill', document.getElementById('fillShape').checked ? '1' : '0');
            formData.append('spacing', document.getElementById('fillSpacing').value);

            try {
                const resp = await fetch('/process', { method: 'POST', body: formData });
                const data = await resp.json();

                if (data.error) {
                    log('Error: ' + data.error);
                    return;
                }

                document.getElementById('stats').style.display = 'grid';
                document.getElementById('pathCount').textContent = data.path_count;
                document.getElementById('pointCount').textContent = data.point_count;
                document.getElementById('estTime').textContent = Math.round(data.est_time) + 's';

                log(`Processed: ${data.path_count} paths, ${data.point_count} points`);

                // Draw edge preview
                drawEdgePreview(data.paths, data.width, data.height);

                // Add as a new layer (this will save current layer first, then add new one)
                const layerName = currentFileName || ('Image ' + (layers.length + 1));
                addLayer(layerName, data.paths, originalImage);

                // Now set processedPaths to the new layer's paths
                processedPaths = JSON.parse(JSON.stringify(data.paths));

                // Reset for next image
                originalImage = null;
                dropZone.innerHTML = '<input type="file" id="imageInput" accept="image/*"><p>📁 Drop image here or click to upload</p>';
                document.getElementById('imageInput').onchange = () => {
                    if (document.getElementById('imageInput').files.length)
                        handleFile(document.getElementById('imageInput').files[0]);
                };

                updatePreview();
                updateDrawButton();
                updatePartsPanel();
            } catch (err) {
                log('Error: ' + err.message);
            }
        }

        async function detectArea() {
            log('Detecting drawing area from phone...');
            document.getElementById('areaStatus').textContent = 'Capturing screenshot...';
            document.getElementById('areaStatus').className = 'status warning';

            try {
                const resp = await fetch('/detect');
                const data = await resp.json();
                handleDetectResult(data);
            } catch (err) {
                document.getElementById('areaStatus').textContent = 'Error: ' + err.message;
                document.getElementById('areaStatus').className = 'status error';
                log('Error: ' + err.message);
            }
        }

        async function detectAreaFromFile(file) {
            if (!file) return;
            log('Detecting drawing area from uploaded screenshot...');
            document.getElementById('areaStatus').textContent = 'Analyzing screenshot...';
            document.getElementById('areaStatus').className = 'status warning';

            try {
                const formData = new FormData();
                formData.append('screenshot', file, file.name);
                const resp = await fetch('/detect-from-file', { method: 'POST', body: formData });
                const data = await resp.json();
                handleDetectResult(data);
            } catch (err) {
                document.getElementById('areaStatus').textContent = 'Error: ' + err.message;
                document.getElementById('areaStatus').className = 'status error';
                log('Error: ' + err.message);
            }
            // Reset input so the same file can be re-selected
            document.getElementById('screenshotInput').value = '';
        }

        function handleDetectResult(data) {
            if (data.error) {
                document.getElementById('areaStatus').textContent = 'Error: ' + data.error;
                document.getElementById('areaStatus').className = 'status error';
                log('Detection error: ' + data.error);
                return;
            }

            drawingArea = data.area;
            document.getElementById('areaStatus').textContent =
                `Area detected: ${data.area.right - data.area.left}x${data.area.bottom - data.area.top}px`;
            document.getElementById('areaStatus').className = 'status success';
            log('Drawing area detected successfully');
            updatePreview();
            updateDrawButton();
        }

        function updatePreview() {
            ctx.fillStyle = '#0a0a1a';
            ctx.fillRect(0, 0, canvas.width, canvas.height);

            if (!drawingArea) {
                ctx.fillStyle = '#333';
                ctx.font = '14px sans-serif';
                ctx.textAlign = 'center';
                ctx.fillText('Click "Detect Area" to see preview', canvas.width/2, canvas.height/2);
                return;
            }

            // Scale factor for preview (phone coords to canvas)
            const area = drawingArea;
            const previewScale = Math.min(
                canvas.width / (area.right - area.left + 100),
                canvas.height / (area.bottom - area.top + 100)
            ) * 0.9;

            const offsetX = (canvas.width - (area.right - area.left) * previewScale) / 2;
            const offsetY = (canvas.height - (area.bottom - area.top) * previewScale) / 2;

            // Transform function
            const tx = (x) => offsetX + (x - area.left) * previewScale;
            const ty = (y) => offsetY + (y - area.top) * previewScale;

            // Draw drawing area boundary
            ctx.strokeStyle = '#333';
            ctx.lineWidth = 2;
            ctx.beginPath();
            ctx.rect(tx(area.left), ty(area.top),
                    (area.right - area.left) * previewScale,
                    (area.bottom - area.top) * previewScale);
            ctx.stroke();

            // Draw exclusion zones
            ctx.fillStyle = 'rgba(255, 0, 0, 0.2)';
            // Top-left exclusion
            ctx.fillRect(tx(area.left), ty(area.top),
                        (area.top_excl_right - area.left) * previewScale,
                        (area.top_excl_bottom - area.top) * previewScale);
            // VISA exclusion
            ctx.fillRect(tx(area.cutout_left), ty(area.cutout_top),
                        (area.right - area.cutout_left) * previewScale,
                        (area.bottom - area.cutout_top) * previewScale);

            // Draw the L-shaped boundary
            ctx.strokeStyle = '#00d4ff';
            ctx.lineWidth = 2;
            ctx.beginPath();
            ctx.moveTo(tx(area.top_excl_right), ty(area.top));
            ctx.lineTo(tx(area.right), ty(area.top));
            ctx.lineTo(tx(area.right), ty(area.cutout_top));
            ctx.lineTo(tx(area.cutout_left), ty(area.cutout_top));
            ctx.lineTo(tx(area.cutout_left), ty(area.bottom));
            ctx.lineTo(tx(area.left), ty(area.bottom));
            ctx.lineTo(tx(area.left), ty(area.top_excl_bottom));
            ctx.lineTo(tx(area.top_excl_right), ty(area.top_excl_bottom));
            ctx.closePath();
            ctx.stroke();

            // Available area (main portion avoiding exclusions)
            const availLeft = Math.max(area.left, area.top_excl_right);
            const availTop = Math.max(area.top, area.top_excl_bottom);
            const availRight = area.cutout_left;
            const availBottom = area.bottom;
            const availW = availRight - availLeft - 40;
            const availH = availBottom - availTop - 40;
            const areaCenterX = availLeft + 20 + availW / 2;
            const areaCenterY = availTop + 20 + availH / 2;

            // Draw all visible layers
            const layerColors = ['#00ff88', '#ff8800', '#ff00ff', '#00ffff', '#ffff00'];
            layers.forEach((layer, layerIdx) => {
                if (!layer.visible || !layer.paths || layer.paths.length === 0) return;

                const isActive = layerIdx === activeLayerIndex;
                ctx.strokeStyle = isActive ? '#00ff88' : layerColors[layerIdx % layerColors.length] + '88';
                ctx.lineWidth = isActive ? 1.5 : 1;

                // Calculate path bounds
                let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
                for (const path of layer.paths) {
                    for (const [x, y] of path) {
                        minX = Math.min(minX, x);
                        minY = Math.min(minY, y);
                        maxX = Math.max(maxX, x);
                        maxY = Math.max(maxY, y);
                    }
                }
                const pathW = maxX - minX || 1;
                const pathH = maxY - minY || 1;
                const pathCenterX = minX + pathW / 2;
                const pathCenterY = minY + pathH / 2;
                const baseScale = Math.min(availW / pathW, availH / pathH);

                // Use active layer's current transforms, or layer's saved transforms
                const lScaleX = isActive ? scaleX : layer.scaleX;
                const lScaleY = isActive ? scaleY : layer.scaleY;
                const lRotation = isActive ? rotation : layer.rotation;
                const lFlipH = isActive ? flipHorizontal : layer.flipH;
                const lFlipV = isActive ? flipVertical : layer.flipV;
                const lOffset = isActive ? imageOffset : layer.offset;

                function transformPoint(px, py) {
                    let x = px - pathCenterX;
                    let y = py - pathCenterY;
                    if (lFlipH) x = -x;
                    if (lFlipV) y = -y;
                    if (lRotation !== 0) {
                        const rad = lRotation * Math.PI / 180;
                        const cos = Math.cos(rad), sin = Math.sin(rad);
                        const rx = x * cos - y * sin;
                        const ry = x * sin + y * cos;
                        x = rx; y = ry;
                    }
                    x *= baseScale * lScaleX;
                    y *= baseScale * lScaleY;
                    x += areaCenterX;
                    y += areaCenterY;
                    return [x, y];
                }

                for (const path of layer.paths) {
                    if (path.length < 2) continue;
                    ctx.beginPath();
                    const [fx, fy] = transformPoint(path[0][0], path[0][1]);
                    ctx.moveTo(tx(fx) + lOffset.x, ty(fy) + lOffset.y);
                    for (let i = 1; i < path.length; i++) {
                        const [px, py] = transformPoint(path[i][0], path[i][1]);
                        ctx.lineTo(tx(px) + lOffset.x, ty(py) + lOffset.y);
                    }
                    ctx.stroke();
                }
            });

            // Draw eraser cursor
            if (currentTool === 'erase' && mousePos.x > 0 && mousePos.y > 0) {
                ctx.strokeStyle = 'rgba(255, 100, 100, 0.8)';
                ctx.lineWidth = 2;
                ctx.setLineDash([4, 4]);
                ctx.beginPath();
                ctx.arc(mousePos.x, mousePos.y, eraserSize, 0, Math.PI * 2);
                ctx.stroke();
                ctx.setLineDash([]);
            }
        }

        function drawEdgePreview(paths, imgW, imgH) {
            const container = document.getElementById('edgePreview');
            const edgeCanvas = document.getElementById('edgeCanvas');
            const ectx = edgeCanvas.getContext('2d');

            container.style.display = 'block';

            // Size canvas to image aspect ratio
            const maxW = 300, maxH = 300;
            const scale = Math.min(maxW / imgW, maxH / imgH);
            edgeCanvas.width = Math.round(imgW * scale);
            edgeCanvas.height = Math.round(imgH * scale);

            // Clear
            ectx.fillStyle = '#111';
            ectx.fillRect(0, 0, edgeCanvas.width, edgeCanvas.height);

            // Draw paths
            ectx.strokeStyle = '#00ff88';
            ectx.lineWidth = 1;

            for (const path of paths) {
                if (path.length < 2) continue;
                ectx.beginPath();
                ectx.moveTo(path[0][0] * scale, path[0][1] * scale);
                for (let i = 1; i < path.length; i++) {
                    ectx.lineTo(path[i][0] * scale, path[i][1] * scale);
                }
                ectx.stroke();
            }
        }

        function updateDrawButton() {
            const btn = document.getElementById('drawBtn');
            const hasVisibleLayers = layers.some(l => l.visible && l.paths && l.paths.length > 0);
            btn.disabled = !(hasVisibleLayers && drawingArea);
        }

        // Collect all paths from visible layers (optionally subsample for Try Mode)
        function collectLayerPaths(subsample = false) {
            const area = drawingArea;
            const previewScale = Math.min(
                canvas.width / (area.right - area.left + 100),
                canvas.height / (area.bottom - area.top + 100)
            ) * 0.9;
            return layers
                .filter(l => l.visible && l.paths && l.paths.length > 0)
                .map(l => {
                    let paths = l.paths;
                    if (subsample) {
                        // Take every 3rd path to give a rough sketch
                        paths = paths.filter((_, i) => i % 3 === 0);
                    }
                    return {
                        paths,
                        original_bounds: l.originalBounds,
                        offset_x: l.offset.x / previewScale,
                        offset_y: l.offset.y / previewScale,
                        scale_x: l.scaleX,
                        scale_y: l.scaleY,
                        rotation: l.rotation,
                        flip_h: l.flipH,
                        flip_v: l.flipV
                    };
                });
        }

        // Slice visible layers within a percentage range of total points
        function sliceLayersForRange(startPct, endPct) {
            const area = drawingArea;
            const previewScale = Math.min(
                canvas.width / (area.right - area.left + 100),
                canvas.height / (area.bottom - area.top + 100)
            ) * 0.9;

            const allVisibleLayers = layers.filter(l => l.visible && l.paths && l.paths.length > 0);
            const totalPoints = allVisibleLayers.reduce((s, l) => s + l.paths.reduce((a, p) => a + p.length, 0), 0);
            
            const startIdx = Math.floor(totalPoints * startPct / 100);
            const endIdx = (endPct >= 100) ? totalPoints : Math.floor(totalPoints * endPct / 100);
            
            let globalIdx = 0;
            return allVisibleLayers.map(l => {
                const layerPaths = [];
                for (const path of l.paths) {
                    const slicedPath = [];
                    for (const pt of path) {
                        // Point is included if index is in [startIdx, endIdx]
                        // We use inclusive end to ensure the next segment starts where this one ends
                        if (globalIdx >= startIdx && globalIdx <= endIdx) {
                            slicedPath.push(pt);
                        }
                        globalIdx++;
                    }
                    if (slicedPath.length >= 2) {
                        layerPaths.push(slicedPath);
                    }
                }
                
                return {
                    paths: layerPaths,
                    original_bounds: l.originalBounds,
                    offset_x: l.offset.x / previewScale,
                    offset_y: l.offset.y / previewScale,
                    scale_x: l.scaleX,
                    scale_y: l.scaleY,
                    rotation: l.rotation,
                    flip_h: l.flipH,
                    flip_v: l.flipV
                };
            }).filter(l => l.paths.length > 0);
        }

        function updatePartsPanel() {
            const allVisibleLayers = layers.filter(l => l.visible && l.paths && l.paths.length > 0);
            const totalPoints = allVisibleLayers.reduce((s, l) => s + l.paths.reduce((a, p) => a + p.length, 0), 0);
            
            document.getElementById('partsPanel').style.display = totalPoints > 0 ? 'block' : 'none';
            if (totalPoints > 0) {
                const startIdx = Math.floor(totalPoints * rangeStartPct / 100);
                const endIdx = Math.floor(totalPoints * rangeEndPct / 100);
                document.getElementById('rangePointsLabel').textContent = `Selection: ${endIdx - startIdx} pts / ${totalPoints}`;
                updateRangeSliderUI();
                updateSplitParts();
                updateTimeEstimate();
                if (isPointsEditorOpen) refreshPointsList();
            }
        }

        function updateSplitParts() {
            const container = document.getElementById('splitPartsContainer');
            const count = parseInt(document.getElementById('splitPartsCount').value) || 1;
            
            container.innerHTML = Array.from({length: count}, (_, i) => {
                const start = (i / count * 100).toFixed(0);
                const end = ((i + 1) / count * 100).toFixed(0);
                return `<button class="btn" style="padding:2px 8px; font-size:10px; background:#1a1a3a; border:1px solid #0f3460;" 
                        onclick="playSplitPart(${i}, ${count})" title="${start}% - ${end}%">P${i+1}</button>`;
            }).join('');
        }

        function playSplitPart(index, total) {
            rangeStartPct = (index / total) * 100;
            rangeEndPct = ((index + 1) / total) * 100;
            updatePartsPanel(); 
            updateTimeEstimate();
        }

        function updateRangeSliderUI() {
            document.getElementById('handleStart').style.left = rangeStartPct + '%';
            document.getElementById('handleEnd').style.left = rangeEndPct + '%';
            document.getElementById('rangeFill').style.left = rangeStartPct + '%';
            document.getElementById('rangeFill').style.width = (rangeEndPct - rangeStartPct) + '%';
            document.getElementById('rangeStartLabel').textContent = `Start: ${Math.round(rangeStartPct)}%`;
            document.getElementById('rangeEndLabel').textContent = `End: ${Math.round(rangeEndPct)}%`;
        }

        function resetRange() {
            rangeStartPct = 0;
            rangeEndPct = 100;
            updatePartsPanel();
        }

        async function startDrawingRange() {
            saveCurrentLayerState();
            const tryMode = document.getElementById('tryMode').checked;
            
            if (tryMode) {
                log('Try Mode: drawing rough sketch of selection...');
                const sketchLayers = sliceLayersForRange(rangeStartPct, rangeEndPct).map(l => ({
                    ...l, 
                    paths: l.paths.filter((_, i) => i % 3 === 0)
                }));
                await runDraw(sketchLayers, 'Sketch done. Now playing full selection...');
                if (!isDrawing) return;
            }
            
            log(`Playing Selection (${Math.round(rangeStartPct)}% - ${Math.round(rangeEndPct)}%)...`);
            await runDraw(sliceLayersForRange(rangeStartPct, rangeEndPct), 'Selection complete!');
        }

        async function playNext() {
            if (rangeStartPct >= 100) {
                log('No more segments to play.');
                return;
            }
            if (rangeEndPct >= 100) {
                log('Finished all points.');
                return;
            }

            const width = rangeEndPct - rangeStartPct;
            rangeStartPct = rangeEndPct;
            rangeEndPct = Math.min(100, rangeStartPct + width);
            
            updatePartsPanel();
            updateTimeEstimate();
            
            log(`Advancing to Next Selection: ${Math.round(rangeStartPct)}% - ${Math.round(rangeEndPct)}%`);
            await startDrawingRange();
        }

        // --- Points Editor Implementation ---
        
        let isPointsEditorOpen = false;

        function togglePointsEditor() {
            isPointsEditorOpen = !isPointsEditorOpen;
            const editor = document.getElementById('pointsEditor');
            const showBtn = document.getElementById('showEditorBtn');
            editor.style.display = isPointsEditorOpen ? 'flex' : 'none';
            showBtn.style.display = isPointsEditorOpen ? 'none' : 'inline-block';
            if (isPointsEditorOpen) refreshPointsList();
        }

        function refreshPointsList() {
            const allVisibleLayers = layers.filter(l => l.visible && l.paths && l.paths.length > 0);
            const totalPoints = allVisibleLayers.reduce((s, l) => s + l.paths.reduce((a, p) => a + p.length, 0), 0);
            const startIdx = Math.floor(totalPoints * rangeStartPct / 100);
            const endIdx = Math.floor(totalPoints * rangeEndPct / 100);
            
            pointSelectionMapping = [];
            let globalPtIdx = 0;
            
            // Generate mapping for current range
            layers.forEach((l, lIdx) => {
                if (!l.visible || !l.paths) return;
                l.paths.forEach((p, pIdx) => {
                    p.forEach((pt, ptIdx) => {
                        if (globalPtIdx >= startIdx && globalPtIdx < endIdx) {
                            pointSelectionMapping.push({lIdx, pIdx, ptIdx});
                        }
                        globalPtIdx++;
                    });
                });
            });

            const grid = document.getElementById('pointsGrid');
            const editorStats = document.getElementById('editorStats');
            
            const selectedCount = pointSelectionMapping.length;
            editorStats.textContent = `${selectedCount} points in selection.`;
            
            // Use a higher limit for performance safety, but much larger than 100
            const displayLimit = 5000;
            const toDisplay = pointSelectionMapping.slice(0, displayLimit);
            
            grid.innerHTML = toDisplay.map((m, i) => {
                const pt = layers[m.lIdx].paths[m.pIdx][m.ptIdx];
                return `
                    <div class="pt-item" title="Layer: ${layers[m.lIdx].name}">
                        <span class="idx">${i + 1}</span>
                        <div class="coord">
                            <span>X</span><input type="number" id="pt-x-${i}" value="${Math.round(pt[0])}">
                            <span>Y</span><input type="number" id="pt-y-${i}" value="${Math.round(pt[1])}">
                        </div>
                    </div>
                `;
            }).join('');
            
            if (selectedCount > displayLimit) {
                grid.innerHTML += `<div style="grid-column: 1/-1; text-align:center; padding:10px; color:#444;">Display limit reached (${displayLimit} points)</div>`;
            }
        }

        function applyPointEdits() {
            const displayLimit = 5000;
            const toUpdate = pointSelectionMapping.slice(0, displayLimit);
            
            let changedCount = 0;
            toUpdate.forEach((m, i) => {
                const elX = document.getElementById(`pt-x-${i}`);
                const elY = document.getElementById(`pt-y-${i}`);
                if (!elX || !elY) return;

                const newX = parseInt(elX.value);
                const newY = parseInt(elY.value);
                const pt = layers[m.lIdx].paths[m.pIdx][m.ptIdx];
                
                if (pt[0] !== newX || pt[1] !== newY) {
                    layers[m.lIdx].paths[m.pIdx][m.ptIdx] = [newX, newY];
                    changedCount++;
                }
            });
            
            if (changedCount > 0) {
                log(`Applied edits to ${changedCount} points.`);
                updatePreview();
                refreshPointsList();
            }
        }

        function bulkDeleteSelection() {
            if (!confirm(`Delete all ${pointSelectionMapping.length} selected points?`)) return;
            
            // Sort mapping in reverse to avoid index shifting issues
            // We group by layer/path to make it easier
            const reverseMapping = [...pointSelectionMapping].sort((a,b) => {
                if (a.lIdx !== b.lIdx) return b.lIdx - a.lIdx;
                if (a.pIdx !== b.pIdx) return b.pIdx - a.pIdx;
                return b.ptIdx - a.ptIdx;
            });
            
            reverseMapping.forEach(m => {
                layers[m.lIdx].paths[m.pIdx].splice(m.ptIdx, 1);
            });
            
            log(`Deleted ${reverseMapping.length} points.`);
            updatePreview();
            refreshPointsList();
            updatePartsPanel();
            
            if (pointSelectionMapping.length === 0) togglePointsEditor();
        }

        function bulkThinSelection() {
            // Remove every 2nd point in the selection
            const toDelete = pointSelectionMapping.filter((_, i) => i % 2 === 1);
            
            const reverseMapping = [...toDelete].sort((a,b) => {
                if (a.lIdx !== b.lIdx) return b.lIdx - a.lIdx;
                if (a.pIdx !== b.pIdx) return b.pIdx - a.pIdx;
                return b.ptIdx - a.ptIdx;
            });
            
            reverseMapping.forEach(m => {
                layers[m.lIdx].paths[m.pIdx].splice(m.ptIdx, 1);
            });
            
            log(`Thinned selection: removed ${reverseMapping.length} points.`);
            updatePreview();
            refreshPointsList();
            updatePartsPanel();
        }

        // Initialize range slider dragging
        const rangeContainer = document.getElementById('rangeContainer');
        const handleStart = document.getElementById('handleStart');
        const handleEnd = document.getElementById('handleEnd');

        const onHandleDown = (e, handle) => {
            e.preventDefault();
            activeHandle = handle;
            document.addEventListener('mousemove', onHandleMove);
            document.addEventListener('mouseup', onHandleUp);
            document.addEventListener('touchmove', onHandleMove, {passive: false});
            document.addEventListener('touchend', onHandleUp);
        };

        const onHandleMove = (e) => {
            if (!activeHandle) return;
            e.preventDefault();
            const rect = rangeContainer.getBoundingClientRect();
            const touch = e.touches ? e.touches[0] : e;
            let pct = (touch.clientX - rect.left) / rect.width * 100;
            pct = Math.max(0, Math.min(100, pct));

            if (activeHandle === 'start') {
                rangeStartPct = Math.min(pct, rangeEndPct - 1);
            } else {
                rangeEndPct = Math.max(pct, rangeStartPct + 1);
            }
            updatePartsPanel();
        };

        const onHandleUp = () => {
            activeHandle = null;
            document.removeEventListener('mousemove', onHandleMove);
            document.removeEventListener('mouseup', onHandleUp);
            document.removeEventListener('touchmove', onHandleMove);
            document.removeEventListener('touchend', onHandleUp);
        };

        handleStart.addEventListener('mousedown', (e) => onHandleDown(e, 'start'));
        handleEnd.addEventListener('mousedown', (e) => onHandleDown(e, 'end'));
        handleStart.addEventListener('touchstart', (e) => onHandleDown(e, 'start'), {passive: false});
        handleEnd.addEventListener('touchstart', (e) => onHandleDown(e, 'end'), {passive: false});

        let isPaused = false;

        async function togglePause() {
            const btn = document.getElementById('pauseBtn');
            if (!isPaused) {
                await fetch('/pause', {method: 'POST'});
                isPaused = true;
                btn.textContent = '▶ Resume';
                btn.style.background = '#27ae60';
                document.getElementById('drawStatus').textContent = 'Drawing paused. Click Resume to continue.';
                document.getElementById('drawStatus').className = 'status warning';
                log('Drawing paused');
            } else {
                await fetch('/resume', {method: 'POST'});
                isPaused = false;
                btn.textContent = '⏸ Pause';
                btn.style.background = '#e67e22';
                document.getElementById('drawStatus').textContent = 'Drawing resumed...';
                document.getElementById('drawStatus').className = 'status warning';
                log('Drawing resumed');
            }
        }





        async function runDraw(layersToSend, doneMsg) {
            isDrawing = true;
            document.getElementById('drawBtn').disabled = true;
            document.getElementById('stopBtn').disabled = false;
            document.getElementById('pauseBtn').disabled = false;
            isPaused = false;
            document.getElementById('pauseBtn').textContent = '⏸ Pause';
            document.getElementById('pauseBtn').style.background = '#e67e22';
            document.getElementById('drawStatus').textContent = 'Drawing in progress...';
            document.getElementById('drawStatus').className = 'status warning';

            const strokeDuration = parseInt(document.getElementById('strokeDuration').value);
            const strokeDelay = parseInt(document.getElementById('strokeDelay').value);

            try {
                const resp = await fetch('/draw', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        layers: layersToSend,
                        area: drawingArea,
                        stroke_duration: strokeDuration,
                        stroke_delay: strokeDelay
                    })
                });

                const reader = resp.body.getReader();
                const decoder = new TextDecoder();

                while (true) {
                    if (!isDrawing) {
                        log('Cancelling draw stream...');
                        await reader.cancel();
                        break;
                    }

                    const {value, done} = await reader.read();
                    if (done) break;
                    const text = decoder.decode(value);
                    const lines = text.split('\\n').filter(l => l.startsWith('data:'));
                    for (const line of lines) {
                        const data = JSON.parse(line.slice(5));
                        if (data.progress !== undefined) {
                            document.getElementById('progressBar').style.width = data.progress + '%';
                            // Karaoke highlight in points editor
                            if (isPointsEditorOpen && pointSelectionMapping.length > 0) {
                                const activePtIdx = Math.floor(data.progress / 100 * pointSelectionMapping.length);
                                document.querySelectorAll('.pt-item').forEach((el, i) => {
                                    el.style.background = i === activePtIdx
                                        ? 'rgba(0,212,255,0.25)'
                                        : (i < activePtIdx ? 'rgba(0,212,255,0.06)' : 'rgba(255,255,255,0.03)');
                                });
                            }
                        }
                        if (data.message) log(data.message);
                        if (data.done) {
                            document.getElementById('drawStatus').textContent = doneMsg;
                            document.getElementById('drawStatus').className = 'status success';
                            // Clear karaoke
                            document.querySelectorAll('.pt-item').forEach(el => el.style.background = '');
                            
                            // Check for auto-play (using an async flow)
                            if (document.getElementById('autoPlay').checked && isDrawing) {
                                (async () => {
                                    await sleep(500); 
                                    if (document.getElementById('autoPlay').checked && isDrawing) {
                                        playNext();
                                    }
                                })();
                            }
                        }
                        if (data.error) {
                            document.getElementById('drawStatus').textContent = 'Error: ' + data.error;
                            document.getElementById('drawStatus').className = 'status error';
                            document.querySelectorAll('.pt-item').forEach(el => el.style.background = '');
                        }
                    }
                }
            } catch (err) {
                log('Error: ' + err.message);
                document.getElementById('drawStatus').textContent = 'Error: ' + err.message;
                document.getElementById('drawStatus').className = 'status error';
            } finally {
                isDrawing = false;
                document.getElementById('drawBtn').disabled = false;
                document.getElementById('stopBtn').disabled = true;
                document.getElementById('pauseBtn').disabled = true;
            }
        }

        // Legacy alias for any remaining calls
        function startDrawing() { startDrawingRange(); }

        async function stopDrawing() {
            await fetch('/stop', {method: 'POST'});
            isDrawing = false;
            isPaused = false;
            document.getElementById('pauseBtn').textContent = '⏸ Pause';
            document.getElementById('pauseBtn').style.background = '#e67e22';
            document.getElementById('pauseBtn').disabled = true;
            log('Drawing stopped by user');
            document.getElementById('drawStatus').textContent = 'Drawing stopped';
            document.getElementById('drawStatus').className = 'status warning';
        }

        function log(msg) {
            const logEl = document.getElementById('log');
            const time = new Date().toLocaleTimeString();
            logEl.textContent = `[${time}] ${msg}\\n` + logEl.textContent;
        }

        // Initial state
        log('Ready. Connect Android via USB and enable USB debugging.');
    </script>
</body>
</html>
'''


@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)


@app.route('/process', methods=['POST'])
def process_image():
    """Process uploaded image and extract paths."""
    try:
        method = request.form.get('method', 'auto')
        threshold = int(request.form.get('threshold', 127))
        simplify = float(request.form.get('simplify', 2.0))
        fill = request.form.get('fill', '0') == '1'
        spacing_raw = request.form.get('spacing', '4')
        try:
            spacing = int(spacing_raw)
        except (TypeError, ValueError):
            return jsonify({'error': 'Invalid spacing value; it must be a positive integer.'}), 400
        if spacing < 1:
            return jsonify({'error': 'Invalid spacing value; it must be at least 1.'}), 400

        # Get uploaded file
        if 'image' not in request.files:
            return jsonify({'error': 'No image uploaded'})

        file = request.files['image']
        img_bytes = file.read()
        img_array = np.frombuffer(img_bytes, dtype=np.uint8)
        img = cv2.imdecode(img_array, cv2.IMREAD_GRAYSCALE)

        if img is None:
            return jsonify({'error': 'Could not decode image'})

        # Resize if too large
        max_size = 500
        h, w = img.shape
        if max(h, w) > max_size:
            scale = max_size / max(h, w)
            img = cv2.resize(img, (int(w * scale), int(h * scale)))

        # Extract paths based on method
        h, w = img.shape
        paths = extract_paths(img, method, threshold, simplify, fill, spacing)

        # Calculate stats
        path_count = len(paths)
        point_count = sum(len(p) for p in paths)
        est_time = point_count * 0.03  # ~30ms per point

        STATE['image_paths'] = paths

        return jsonify({
            'paths': paths,
            'path_count': path_count,
            'point_count': point_count,
            'est_time': est_time,
            'width': w,
            'height': h
        })

    except Exception as e:
        return jsonify({'error': str(e)})


def extract_paths(img, method, threshold, simplify, fill=False, spacing=4):
    """Extract drawable paths from image."""
    if method == 'auto':
        std_dev = np.std(img)
        method = 'contours' if std_dev > 70 else 'edges'

    binary = None
    if method == 'edges':
        blurred = cv2.GaussianBlur(img, (5, 5), 0)
        high_thresh, _ = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        edges = cv2.Canny(blurred, high_thresh * 0.5, high_thresh)
        contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        binary = edges
    elif method == 'contours':
        _, binary = cv2.threshold(img, threshold, 255, cv2.THRESH_BINARY_INV)
        contours, _ = cv2.findContours(binary, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    elif method == 'contours_inv':
        _, binary = cv2.threshold(img, threshold, 255, cv2.THRESH_BINARY)
        contours, _ = cv2.findContours(binary, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    elif method == 'adaptive':
        binary = cv2.adaptiveThreshold(img, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                        cv2.THRESH_BINARY_INV, 11, 2)
        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    else:
        contours = []
        binary = np.zeros_like(img)

    paths = []
    
    if fill and binary is not None:
        h, w = binary.shape
        fill_paths = []
        for y in range(0, h, spacing):
            row = binary[y, :]
            # Find continuous segments of white pixels (255)
            diff = np.diff(np.concatenate(([0], row, [0])))
            starts = np.where(diff > 0)[0]
            ends = np.where(diff < 0)[0]
            
            segments = []
            for s, e in zip(starts, ends):
                if e - s > 1: # Ignore 1-pixel artifacts
                    segments.append((s, e))
            
            # Zig-zag to minimize pen travel time
            if len(segments) > 0:
                if y % (spacing * 2) != 0:
                    segments.reverse()
                    for s, e in segments:
                        fill_paths.append([(int(e-1), int(y)), (int(s), int(y))])
                else:
                    for s, e in segments:
                        fill_paths.append([(int(s), int(y)), (int(e-1), int(y))])

        paths.extend(fill_paths)

    for contour in contours:
        if len(contour) < 3:
            continue
        if cv2.contourArea(contour) < 20 and not fill:
            continue

        if simplify > 0:
            contour = cv2.approxPolyDP(contour, simplify, True)

        path = [[int(p[0][0]), int(p[0][1])] for p in contour]
        if len(path) >= 2:
            path.append(path[0])  # Close path
            paths.append(path)

    return paths


@app.route('/detect')
def detect_area():
    """Detect drawing area from phone screenshot."""
    try:
        area = detect_from_screenshot(debug=False)
        STATE['drawing_area'] = area

        return jsonify({
            'area': {
                'top': area.top,
                'left': area.left,
                'right': area.right,
                'bottom': area.bottom,
                'cutout_left': area.cutout_left,
                'cutout_top': area.cutout_top,
                'top_excl_right': area.top_excl_right,
                'top_excl_bottom': area.top_excl_bottom
            }
        })
    except Exception as e:
        return jsonify({'error': str(e)})


@app.route('/detect-from-file', methods=['POST'])
def detect_area_from_file():
    """Detect drawing area from an uploaded screenshot."""
    try:
        if 'screenshot' not in request.files:
            return jsonify({'error': 'No screenshot uploaded'})
        file = request.files['screenshot']
        screenshot_path = 'screen.png'
        file.save(screenshot_path)

        area = detect_from_screenshot(screenshot_path=screenshot_path, debug=False)
        STATE['drawing_area'] = area

        return jsonify({
            'area': {
                'top': area.top,
                'left': area.left,
                'right': area.right,
                'bottom': area.bottom,
                'cutout_left': area.cutout_left,
                'cutout_top': area.cutout_top,
                'top_excl_right': area.top_excl_right,
                'top_excl_bottom': area.top_excl_bottom
            }
        })
    except Exception as e:
        return jsonify({'error': str(e)})


@app.route('/draw', methods=['POST'])
def draw():
    """Draw paths on phone via ADB."""
    # Extract data from request before entering generator
    data = request.json
    input_layers = data.get('layers', [])
    area = data['area']
    stroke_duration = data.get('stroke_duration', 60)
    stroke_delay = data.get('stroke_delay', 15) / 1000.0  # Convert ms to seconds

    def generate():
        try:
            # Convert area dict to DrawingArea
            drawing_area = DrawingArea(
                top=area['top'],
                left=area['left'],
                right=area['right'],
                bottom=area['bottom'],
                cutout_left=area['cutout_left'],
                cutout_top=area['cutout_top'],
                top_excl_right=area['top_excl_right'],
                top_excl_bottom=area['top_excl_bottom']
            )

            # Available area
            avail_left = max(drawing_area.left, drawing_area.top_excl_right) + 20
            avail_top = max(drawing_area.top, drawing_area.top_excl_bottom) + 20
            avail_right = drawing_area.cutout_left - 20
            avail_bottom = drawing_area.bottom - 20
            avail_w = avail_right - avail_left
            avail_h = avail_bottom - avail_top
            center_x = avail_left + avail_w / 2
            center_y = avail_top + avail_h / 2

            # Process all layers and collect all paths
            all_scaled_paths = []

            for layer in input_layers:
                paths = layer['paths']
                offset_x = layer.get('offset_x', 0)
                offset_y = layer.get('offset_y', 0)
                scale_x = layer.get('scale_x', 1.0)
                scale_y = layer.get('scale_y', 1.0)
                rot = layer.get('rotation', 0)
                flip_h = layer.get('flip_h', False)
                flip_v = layer.get('flip_v', False)

                if not paths:
                    continue

                # Use original bounds if provided (important for "Parts" feature)
                orig_bounds = layer.get('original_bounds')
                if orig_bounds:
                    min_x = orig_bounds['minX']
                    min_y = orig_bounds['minY']
                    max_x = orig_bounds['maxX']
                    max_y = orig_bounds['maxY']
                else:
                    # Calculate path bounds for this layer (fallback)
                    min_x = min(p[0] for path in paths for p in path)
                    min_y = min(p[1] for path in paths for p in path)
                    max_x = max(p[0] for path in paths for p in path)
                    max_y = max(p[1] for path in paths for p in path)
                path_w = max_x - min_x or 1
                path_h = max_y - min_y or 1
                path_center_x = min_x + path_w / 2
                path_center_y = min_y + path_h / 2
                base_scale = min(avail_w / path_w, avail_h / path_h)

                # Transform function for this layer
                def transform_point(px, py, pcx=path_center_x, pcy=path_center_y,
                                   bs=base_scale, sx=scale_x, sy=scale_y,
                                   r=rot, fh=flip_h, fv=flip_v, ox=offset_x, oy=offset_y):
                    x = px - pcx
                    y = py - pcy
                    if fh: x = -x
                    if fv: y = -y
                    if r != 0:
                        rad = math.radians(r)
                        cos_r, sin_r = math.cos(rad), math.sin(rad)
                        rx = x * cos_r - y * sin_r
                        ry = x * sin_r + y * cos_r
                        x, y = rx, ry
                    x *= bs * sx
                    y *= bs * sy
                    x += center_x + ox
                    y += center_y + oy
                    return int(x), int(y)

                # Transform paths for this layer
                for path in paths:
                    scaled_path = []
                    for px, py in path:
                        sx, sy = transform_point(px, py)
                        if drawing_area.is_inside(sx, sy):
                            scaled_path.append((sx, sy))
                    if len(scaled_path) >= 2:
                        all_scaled_paths.append(scaled_path)

            scaled_paths = all_scaled_paths

            total_paths = len(scaled_paths)
            total_points = sum(len(p) for p in scaled_paths)

            yield f"data:{json.dumps({'message': f'Drawing {total_paths} paths ({total_points} points)...'})}\n\n"

            for i, path in enumerate(scaled_paths):
                for j in range(len(path) - 1):
                    # Pause support: poll state until resumed
                    if STATE.get('paused', False):
                        yield f"data:{json.dumps({'message': 'Paused...'})}\n\n"
                        while STATE.get('paused', False):
                            # Check for stop while paused
                            if not STATE.get('drawing', True):
                                yield f"data:{json.dumps({'message': 'Stopped', 'done': True})}\n\n"
                                return
                            time.sleep(0.1)
                        yield f"data:{json.dumps({'message': 'Resumed.'})}\n\n"

                    if not STATE.get('drawing', True):
                        yield f"data:{json.dumps({'message': 'Stopped', 'done': True})}\n\n"
                        return
                    
                    x1, y1 = path[j]
                    x2, y2 = path[j + 1]
                    subprocess.run(
                        ['adb', 'shell', 'input', 'swipe',
                         str(x1), str(y1), str(x2), str(y2), str(stroke_duration)],
                        capture_output=True
                    )
                    time.sleep(stroke_delay)

                progress = int((i + 1) / total_paths * 100)
                yield f"data:{json.dumps({'progress': progress})}\n\n"

            yield f"data:{json.dumps({'message': 'Complete!', 'done': True, 'progress': 100})}\n\n"

        except Exception as e:
            yield f"data:{json.dumps({'error': str(e)})}\n\n"

    STATE['drawing'] = True
    STATE['paused'] = False
    return app.response_class(generate(), mimetype='text/event-stream')


@app.route('/stop', methods=['POST'])
def stop():
    """Stop drawing."""
    STATE['drawing'] = False
    STATE['paused'] = False
    return jsonify({'status': 'stopped'})


@app.route('/pause', methods=['POST'])
def pause():
    """Pause drawing after current stroke."""
    STATE['paused'] = True
    return jsonify({'status': 'paused'})


@app.route('/resume', methods=['POST'])
def resume():
    """Resume a paused drawing."""
    STATE['paused'] = False
    return jsonify({'status': 'resumed'})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='RevoDraw - Card Drawing Web UI')
    parser.add_argument('-p', '--port', type=int, default=5000, help='Port to run the server on (default: 5000)')
    args = parser.parse_args()
    port = args.port

    print("\n" + "="*50)
    print("🎨 RevoDraw - Card Drawing Web UI")
    print("="*50)
    print("\n📱 Connect your Android phone via USB")
    print("   Enable USB Debugging (Security Settings) on Xiaomi")
    print(f"\n🌐 Open in browser: http://localhost:{port}")
    print("\n" + "="*50 + "\n")

    app.run(host='127.0.0.1', port=port, debug=False, threaded=True)
