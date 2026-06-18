import { useEffect, useMemo, useRef, useState, type ChangeEvent, type MouseEvent as ReactMouseEvent, type WheelEvent as ReactWheelEvent } from 'react';
import { askDiagram, calibrateDiagramScale, deleteDiagram, diagramImageUrl, getCompanyDetail, getCompanyDistrictStats, getLandUseDataset, getPoiDistrictStats, listCompaniesInBounds, listDiagrams, listPoiCategories, listPoisInBounds, recalibrateDiagramLegend, renameDiagram, streamAskDiagram, uploadDiagram } from './api/client';
import type { AskStreamEvent, CompanyDetail, CompanyPoint, Diagram, LandUseDataset, LandUsePolygonFeature, PoiCategory, PoiPoint, Point, RegionShape } from './types';

type AMapPolygonPath = [number, number][][] | [number, number][][][];

declare global {
  interface Window {
    AMap?: {
      Map: new (
        container: string | HTMLElement,
        options?: {
          viewMode?: string;
          zoom?: number;
          center?: [number, number];
          resizeEnable?: boolean;
          mapStyle?: string;
        },
      ) => {
        destroy?: () => void;
        setFitView?: () => void;
        resize?: () => void;
        clearMap?: () => void;
        setCenter?: (center: [number, number]) => void;
        lngLatToContainer?: (lnglat: [number, number] | { lng: number; lat: number }) => { x: number; y: number };
        on?: (event: string, handler: () => void) => void;
        off?: (event: string, handler: () => void) => void;
        getBounds?: () => {
          getSouthWest: () => { lng: number; lat: number };
          getNorthEast: () => { lng: number; lat: number };
        };
        setZoom?: (zoom: number) => void;
        setLayers?: (layers: unknown[]) => void;
      };
      TileLayer: {
        new (): unknown;
        Satellite: new () => unknown;
        RoadNet: new () => unknown;
      };
      Marker: new (options: {
        position: [number, number];
        title?: string;
        extData?: unknown;
        content?: string;
        offset?: [number, number];
        map?: unknown;
      }) => {
        on?: (event: string, handler: () => void) => void;
        getExtData?: () => unknown;
        emit?: (event: string) => void;
        setMap?: (map: unknown | null) => void;
      };
      Polyline: new (options: {
        path: [number, number][];
        strokeColor?: string;
        strokeWeight?: number;
        strokeOpacity?: number;
        strokeStyle?: 'solid' | 'dashed';
        lineJoin?: string;
        map?: unknown;
      }) => {
        setMap?: (map: unknown | null) => void;
      };
      Text: new (options: {
        text: string;
        position: [number, number];
        offset?: [number, number];
        style?: Record<string, string | number>;
        map?: unknown;
      }) => {
        setMap?: (map: unknown | null) => void;
      };
      InfoWindow: new (options: {
        offset?: [number, number];
        content?: string;
      }) => {
        open?: (map: unknown, position: [number, number]) => void;
        close?: () => void;
      };
      Polygon: new (options: {
        path: AMapPolygonPath;
        strokeColor?: string;
        strokeWeight?: number;
        strokeOpacity?: number;
        fillColor?: string;
        fillOpacity?: number;
        zIndex?: number;
        bubble?: boolean;
        extData?: unknown;
        map?: unknown;
      }) => {
        on?: (event: string, handler: (event: { target?: unknown; lnglat?: { lng: number; lat: number } }) => void) => void;
        getExtData?: () => unknown;
        setOptions?: (options: {
          strokeColor?: string;
          strokeWeight?: number;
          strokeOpacity?: number;
          fillColor?: string;
          fillOpacity?: number;
        }) => void;
        setMap?: (map: unknown | null) => void;
      };
      Circle: new (options: {
        center: [number, number];
        radius: number;
        strokeColor?: string;
        strokeWeight?: number;
        strokeOpacity?: number;
        fillColor?: string;
        fillOpacity?: number;
        zIndex?: number;
        bubble?: boolean;
        extData?: unknown;
        map?: unknown;
      }) => {
        setMap?: (map: unknown | null) => void;
        getCenter?: () => { lng: number; lat: number };
        getRadius?: () => number;
      };
      MouseTool?: new (map: unknown) => {
        polygon?: (options?: {
          strokeColor?: string;
          strokeWeight?: number;
          strokeOpacity?: number;
          fillColor?: string;
          fillOpacity?: number;
        }) => void;
        rectangle?: (options?: {
          strokeColor?: string;
          strokeWeight?: number;
          strokeOpacity?: number;
          fillColor?: string;
          fillOpacity?: number;
        }) => void;
        circle?: (options?: {
          strokeColor?: string;
          strokeWeight?: number;
          strokeOpacity?: number;
          fillColor?: string;
          fillOpacity?: number;
        }) => void;
        close?: (ifClear?: boolean) => void;
        on?: (event: string, handler: (event: { type?: string; obj?: unknown }) => void) => void;
        off?: (event: string, handler: (event: { type?: string; obj?: unknown }) => void) => void;
      };
      plugin?: (plugins: string | string[], callback: () => void) => void;
      PlaceSearch?: new (options?: {
        pageSize?: number;
        pageIndex?: number;
        city?: string;
        citylimit?: boolean;
      }) => {
        search?: (
          keyword: string,
          callback: (
            status: string,
            result: {
              poiList?: {
                pois?: Array<{
                  location?: { lng?: number; lat?: number };
                }>;
              };
            },
          ) => void,
        ) => void;
      };
    };
  }
}

type AMapInstance = {
  destroy?: () => void;
  setFitView?: () => void;
  resize?: () => void;
  clearMap?: () => void;
  setCenter?: (center: [number, number]) => void;
  lngLatToContainer?: (lnglat: [number, number] | { lng: number; lat: number }) => { x: number; y: number };
  getZoom?: () => number;
  getCenter?: () => { lng: number; lat: number };
  setZoom?: (zoom: number) => void;
  setLayers?: (layers: unknown[]) => void;
  on?: (event: string, handler: () => void) => void;
  off?: (event: string, handler: () => void) => void;
  getBounds?: () => {
    getSouthWest: () => { lng: number; lat: number };
    getNorthEast: () => { lng: number; lat: number };
  };
};

type ChatMessage = {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  meta?: Record<string, unknown>;
};

type ChatImageAttachment = {
  name: string;
  dataUrl: string;
  mimeType: string;
};

type RenderTable = {
  title?: string;
  headers: string[];
  rows: string[][];
  footnote?: string;
};

type CompanyLayerStatus =
  | { state: 'idle'; message: string }
  | { state: 'loading'; message: string }
  | { state: 'ready'; message: string }
  | { state: 'error'; message: string };

type AMapMarker = {
  on?: (event: string, handler: () => void) => void;
  getExtData?: () => unknown;
  emit?: (event: string) => void;
  setMap?: (map: unknown | null) => void;
};

type AMapOverlayLike = {
  setMap?: (map: unknown | null) => void;
};

type AMapPolygon = {
  on?: (event: string, handler: (event: { target?: unknown; lnglat?: { lng: number; lat: number } }) => void) => void;
  getExtData?: () => unknown;
  getPath?: () => unknown;
  setOptions?: (options: {
    strokeColor?: string;
    strokeWeight?: number;
    strokeOpacity?: number;
    fillColor?: string;
    fillOpacity?: number;
  }) => void;
  setMap?: (map: unknown | null) => void;
};

type AMapCircle = {
  setMap?: (map: unknown | null) => void;
  getCenter?: () => { lng: number; lat: number };
  getRadius?: () => number;
};

type AMapRectangle = {
  setMap?: (map: unknown | null) => void;
  getBounds?: () => {
    getSouthWest: () => { lng: number; lat: number };
    getNorthEast: () => { lng: number; lat: number };
  };
};

type AMapMouseTool = {
  polygon?: (options?: {
    strokeColor?: string;
    strokeWeight?: number;
    strokeOpacity?: number;
    fillColor?: string;
    fillOpacity?: number;
  }) => void;
  rectangle?: (options?: {
    strokeColor?: string;
    strokeWeight?: number;
    strokeOpacity?: number;
    fillColor?: string;
    fillOpacity?: number;
  }) => void;
  circle?: (options?: {
    strokeColor?: string;
    strokeWeight?: number;
    strokeOpacity?: number;
    fillColor?: string;
    fillOpacity?: number;
  }) => void;
  close?: (ifClear?: boolean) => void;
  on?: (event: string, handler: (event: { type?: string; obj?: unknown }) => void) => void;
  off?: (event: string, handler: (event: { type?: string; obj?: unknown }) => void) => void;
};

const COMPANY_MARKER_LIMIT = 300;
const COMPANY_MIN_ZOOM = 13;
const POI_MARKER_LIMIT = 1000;
const POI_MIN_ZOOM = 13;
const LAND_USE_DEFAULT_FILL = '#d6b98b';
const LAND_USE_COLOR_BY_CODE: Record<string, string> = {
  R: '#FFF77F',
  'A1/A2': '#F07AD7',
  A3: '#FF9B7A',
  A4: '#A7E500',
  A5: '#F57297',
  A6: '#A61E23',
  B: '#FF1712',
  'B+R': '#FF8A0A',
  B4: '#7CC3E2',
  U31: '#5F8DBE',
  G1: '#18FF00',
  H14: '#1FA0D2',
  E1: '#20DDE8',
  E2: '#74EE94',
  S4: '#BFBFBF',
  U12: '#1E73D6',
  U21: '#68A9C1',
};
const LAND_USE_COLOR_BY_NATURE: Record<string, string> = {
  居住用地: LAND_USE_COLOR_BY_CODE.R,
  行政办公或文化设施用地: LAND_USE_COLOR_BY_CODE['A1/A2'],
  教育用地: LAND_USE_COLOR_BY_CODE.A3,
  体育用地: LAND_USE_COLOR_BY_CODE.A4,
  医疗用地: LAND_USE_COLOR_BY_CODE.A5,
  社会福利用地: LAND_USE_COLOR_BY_CODE.A6,
  商业用地: LAND_USE_COLOR_BY_CODE.B,
  商住用地: LAND_USE_COLOR_BY_CODE['B+R'],
  公用设施营业网点用地: LAND_USE_COLOR_BY_CODE.B4,
  消防用地: LAND_USE_COLOR_BY_CODE.U31,
  公园绿地: LAND_USE_COLOR_BY_CODE.G1,
  公园用地: LAND_USE_COLOR_BY_CODE.G1,
  村庄建设用地: LAND_USE_COLOR_BY_CODE.H14,
  水域: LAND_USE_COLOR_BY_CODE.E1,
  农林用地: LAND_USE_COLOR_BY_CODE.E2,
  交通场站用地: LAND_USE_COLOR_BY_CODE.S4,
  供电用地: LAND_USE_COLOR_BY_CODE.U12,
  排水用地: LAND_USE_COLOR_BY_CODE.U21,
  规划待定用地: '#545454',
};
const POI_CATEGORY_COLORS = [
  '#ff0000',
  '#ff7a00',
  '#ffe600',
  '#66e000',
  '#20c8d8',
  '#1a39f5',
  '#7a2cff',
  '#ff0078',
  '#f58ac0',
  '#18c3bb',
  '#c000ff',
  '#c8ff00',
  '#42aaff',
] as const;
const MAP_SHAPE_STYLE = {
  strokeColor: '#38bdf8',
  strokeWeight: 2,
  strokeOpacity: 0.95,
  fillColor: '#38bdf8',
  fillOpacity: 0.12,
  zIndex: 1000,
} as const;
const COMPANY_DISTRICTS = ['全部', '禅城区', '南海区', '顺德区', '三水区', '高明区'] as const;
const COMPANY_LIST_PREVIEW_LIMIT = 12;
const DIAGRAM_ZOOM_MIN = 0.5;
const DIAGRAM_ZOOM_MAX = 5;
const DIAGRAM_ZOOM_STEP = 0.25;
const DEFAULT_MAP_VIEW = { center: [112.9128, 23.2023] as [number, number], zoom: 12 } as const;
const RESIZER_SIZE = 10;
const LIBRARY_WIDTH_RANGE = { min: 220, max: 420, default: 260, snaps: [240, 260, 280, 320, 360] } as const;
const CHAT_WIDTH_RANGE = { min: 320, max: 1000, default: 390, snaps: [340, 390, 440, 500, 560, 620, 680, 780, 900, 1000] } as const;
const COMPANY_DRAWER_WIDTH_RANGE = { min: 280, max: 460, default: 340, snaps: [300, 340, 380, 420] } as const;
const BELOW_INFO_HEIGHT_RANGE = { min: 180, max: 420, default: 248, collapsed: 56, snaps: [220, 248, 280, 340, 400] } as const;
const STORAGE_KEYS = {
  libraryWidth: 'planning-ai.library-width',
  chatWidth: 'planning-ai.chat-width',
  companyDrawerWidth: 'planning-ai.company-drawer-width',
  belowInfoHeight: 'planning-ai.below-info-height',
  taskHint: 'planning-ai.task-hint',
  conversationMap: 'planning-ai.dify-conversations',
} as const;
type ChatMode = 'analysis' | 'knowledge' | 'industry';
const CHAT_MODE_CONFIG: Record<ChatMode, { label: string; icon: string }> = {
  analysis: { label: '数据分析', icon: '📊' },
  knowledge: { label: '知识库问答', icon: '📚' },
  industry: { label: '企业关联', icon: '🔗' },
};
const CHAT_MODE_ORDER: ChatMode[] = ['analysis', 'knowledge', 'industry'];

function normalizeStoredChatMode(value: string | null): ChatMode {
  if (value === 'analysis' || value === '计算面积') return 'analysis';
  if (value === 'industry' || value === '企业关联') return 'industry';
  if (value === 'knowledge' || value === 'dify' || value === '规划文本问答' || value === '上传规划文本解读' || value === '土地利用图识别' || value === '图纸+规则综合分析') {
    return 'knowledge';
  }
  return 'analysis';
}

function readStoredSize(key: string, fallback: number, min: number, max: number) {
  if (typeof window === 'undefined') return fallback;
  const raw = window.localStorage.getItem(key);
  if (raw === null) return fallback;
  const parsed = Number(raw);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.min(max, Math.max(min, parsed));
}

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}

function snapSize(value: number, snaps: readonly number[], threshold = 14) {
  const matched = snaps.find((candidate) => Math.abs(candidate - value) <= threshold);
  return matched ?? value;
}

function appendThinkingStep(
  current: { label: string; detail: string }[],
  next: { label: string; detail: string },
) {
  if (current.some((item) => item.label === next.label && item.detail === next.detail)) return current;
  return [...current, next];
}

function readFileAsDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error('图片读取失败'));
    reader.onload = () => resolve(String(reader.result ?? ''));
    reader.readAsDataURL(file);
  });
}

function getConversationStorageKey(diagramId: number | null, mode: 'text' | 'image', taskHint: string) {
  if (diagramId === null) return null;
  return `${diagramId}:${mode}:${taskHint}`;
}

function buildPoiCategoryColorMap(categoryNames: string[]) {
  return categoryNames.reduce<Record<string, string>>((accumulator, categoryName, index) => {
    accumulator[categoryName] = POI_CATEGORY_COLORS[index % POI_CATEGORY_COLORS.length];
    return accumulator;
  }, {});
}

function clampRgb(value: number) {
  return Math.max(0, Math.min(255, Math.round(value)));
}

function adjustHexColor(hex: string, delta: number) {
  const normalized = hex.trim();
  const matched = /^#?([0-9a-f]{6})$/i.exec(normalized);
  if (!matched) return normalized.startsWith('#') ? normalized : `#${normalized}`;
  const raw = matched[1];
  const red = clampRgb(parseInt(raw.slice(0, 2), 16) + delta);
  const green = clampRgb(parseInt(raw.slice(2, 4), 16) + delta);
  const blue = clampRgb(parseInt(raw.slice(4, 6), 16) + delta);
  return `#${red.toString(16).padStart(2, '0')}${green.toString(16).padStart(2, '0')}${blue.toString(16).padStart(2, '0')}`.toUpperCase();
}

function getLandUseFeatureColor(feature: LandUsePolygonFeature) {
  const code = String(feature.properties['用地代码'] ?? '').trim().toUpperCase();
  if (code && LAND_USE_COLOR_BY_CODE[code]) return LAND_USE_COLOR_BY_CODE[code];

  const nature = String(feature.properties['用地性质'] ?? '').trim();
  if (nature && LAND_USE_COLOR_BY_NATURE[nature]) return LAND_USE_COLOR_BY_NATURE[nature];

  const label = String(feature.properties.interactive_label ?? '').trim();
  if (label && LAND_USE_COLOR_BY_NATURE[label]) return LAND_USE_COLOR_BY_NATURE[label];

  return LAND_USE_DEFAULT_FILL;
}

function getLandUsePolygonStyle(feature: LandUsePolygonFeature, state: 'base' | 'hover' | 'active') {
  const fillColor = getLandUseFeatureColor(feature);
  const strokeColor = adjustHexColor(fillColor, -92);
  if (state === 'active') {
    return {
      fillColor,
      fillOpacity: 0.72,
      strokeColor,
      strokeWeight: 3.2,
      strokeOpacity: 0.98,
    };
  }
  if (state === 'hover') {
    return {
      fillColor,
      fillOpacity: 0.58,
      strokeColor,
      strokeWeight: 2.6,
      strokeOpacity: 0.96,
    };
  }
  return {
    fillColor,
    fillOpacity: 0.44,
    strokeColor,
    strokeWeight: 1.8,
    strokeOpacity: 0.92,
  };
}

function scalePoint(point: Point, display: { width: number; height: number }, image: Diagram) {
  return {
    x: (point.x / display.width) * image.image_width,
    y: (point.y / display.height) * image.image_height,
  };
}

function imagePointToDisplayPoint(point: Point, display: { width: number; height: number }, image: Diagram) {
  return {
    x: (point.x / image.image_width) * display.width,
    y: (point.y / image.image_height) * display.height,
  };
}

function imageRadiusToDisplayRadius(radius: number, displayWidth: number, image: Diagram) {
  return (radius / image.image_width) * displayWidth;
}

function fitDiagramSize(diagram: Diagram | null, viewport: { width: number; height: number }) {
  if (diagram === null) return { width: 1, height: 1 };
  const widthLimit = Math.max(viewport.width, 1);
  const heightLimit = Math.max(viewport.height, 1);
  const scale = Math.min(1, widthLimit / diagram.image_width, heightLimit / diagram.image_height);
  if (!Number.isFinite(scale) || scale <= 0) return { width: 1, height: 1 };
  return {
    width: Math.max(1, diagram.image_width * scale),
    height: Math.max(1, diagram.image_height * scale),
  };
}

function clampZoom(value: number) {
  return clamp(value, DIAGRAM_ZOOM_MIN, DIAGRAM_ZOOM_MAX);
}

function formatNumber(value: unknown, digits = 3) {
  const number = Number(value);
  if (!Number.isFinite(number)) return '—';
  return number.toFixed(digits);
}

function formatDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' });
}

function buildLandUsePolygonPath(feature: LandUsePolygonFeature): AMapPolygonPath {
  if (feature.geometry.type === 'Polygon') {
    return feature.geometry.coordinates.map((ring) => ring.map(([lng, lat]) => [lng, lat] as [number, number]));
  }
  return feature.geometry.coordinates.map((polygon) => (
    polygon.map((ring) => ring.map(([lng, lat]) => [lng, lat] as [number, number]))
  ));
}

function getLandUseGeometryLabel(feature: LandUsePolygonFeature) {
  return feature.geometry.type;
}

function countLandUseVertices(feature: LandUsePolygonFeature) {
  if (feature.geometry.type === 'Polygon') {
    return feature.geometry.coordinates.reduce((count, ring) => count + ring.length, 0);
  }
  return feature.geometry.coordinates.reduce(
    (count, polygon) => count + polygon.reduce((ringCount, ring) => ringCount + ring.length, 0),
    0,
  );
}

function getLandUseAnchor(feature: LandUsePolygonFeature): [number, number] {
  if (feature.geometry.type === 'Polygon') {
    const point = feature.geometry.coordinates[0]?.[0];
    return point ? [point[0], point[1]] : [0, 0];
  }
  const point = feature.geometry.coordinates[0]?.[0]?.[0];
  return point ? [point[0], point[1]] : [0, 0];
}

function projectLngLatToMeters(lng: number, lat: number, referenceLatRad: number) {
  const earthRadius = 6378137;
  const lngRad = (lng * Math.PI) / 180;
  const latRad = (lat * Math.PI) / 180;
  return {
    x: earthRadius * lngRad * Math.cos(referenceLatRad),
    y: earthRadius * latRad,
  };
}

function calculateRingAreaSquareMeters(ring: number[][]) {
  if (ring.length < 4) return 0;
  const latitudes = ring.map((point) => point[1]).filter((value) => Number.isFinite(value));
  const averageLat = latitudes.length > 0 ? latitudes.reduce((sum, value) => sum + value, 0) / latitudes.length : 0;
  const referenceLatRad = (averageLat * Math.PI) / 180;
  let doubleArea = 0;
  for (let index = 0; index < ring.length - 1; index += 1) {
    const current = ring[index];
    const next = ring[index + 1];
    const currentPoint = projectLngLatToMeters(current[0], current[1], referenceLatRad);
    const nextPoint = projectLngLatToMeters(next[0], next[1], referenceLatRad);
    doubleArea += currentPoint.x * nextPoint.y - nextPoint.x * currentPoint.y;
  }
  return Math.abs(doubleArea) / 2;
}

function calculatePolygonAreaSquareMeters(rings: number[][][]) {
  if (rings.length === 0) return 0;
  const outerArea = calculateRingAreaSquareMeters(rings[0]);
  const holeArea = rings.slice(1).reduce((sum, ring) => sum + calculateRingAreaSquareMeters(ring), 0);
  return Math.max(0, outerArea - holeArea);
}

function calculateLandUseFeatureAreaSquareMeters(feature: LandUsePolygonFeature) {
  if (feature.geometry.type === 'Polygon') {
    return calculatePolygonAreaSquareMeters(feature.geometry.coordinates);
  }
  return feature.geometry.coordinates.reduce((sum, polygon) => sum + calculatePolygonAreaSquareMeters(polygon), 0);
}

function getLandUseFeatureCenter(feature: LandUsePolygonFeature): Point {
  let minLng = Number.POSITIVE_INFINITY;
  let maxLng = Number.NEGATIVE_INFINITY;
  let minLat = Number.POSITIVE_INFINITY;
  let maxLat = Number.NEGATIVE_INFINITY;
  const consumePoint = ([lng, lat]: number[]) => {
    minLng = Math.min(minLng, lng);
    maxLng = Math.max(maxLng, lng);
    minLat = Math.min(minLat, lat);
    maxLat = Math.max(maxLat, lat);
  };
  if (feature.geometry.type === 'Polygon') {
    feature.geometry.coordinates.forEach((ring) => ring.forEach(consumePoint));
  } else {
    feature.geometry.coordinates.forEach((polygon) => polygon.forEach((ring) => ring.forEach(consumePoint)));
  }
  if (!Number.isFinite(minLng) || !Number.isFinite(minLat) || !Number.isFinite(maxLng) || !Number.isFinite(maxLat)) {
    const [lng, lat] = getLandUseAnchor(feature);
    return { x: lng, y: lat };
  }
  return { x: (minLng + maxLng) / 2, y: (minLat + maxLat) / 2 };
}

function isPointInsidePolygon(point: Point, polygon: Point[]) {
  let inside = false;
  for (let currentIndex = 0, previousIndex = polygon.length - 1; currentIndex < polygon.length; previousIndex = currentIndex, currentIndex += 1) {
    const current = polygon[currentIndex];
    const previous = polygon[previousIndex];
    const intersects = ((current.y > point.y) !== (previous.y > point.y))
      && (point.x < ((previous.x - current.x) * (point.y - current.y)) / ((previous.y - current.y) || Number.EPSILON) + current.x);
    if (intersects) inside = !inside;
  }
  return inside;
}

function getDistanceMetersBetweenPoints(start: Point, end: Point) {
  const toRadians = (value: number) => (value * Math.PI) / 180;
  const earthRadius = 6378137;
  const deltaLat = toRadians(end.y - start.y);
  const deltaLng = toRadians(end.x - start.x);
  const startLat = toRadians(start.y);
  const endLat = toRadians(end.y);
  const sinLat = Math.sin(deltaLat / 2);
  const sinLng = Math.sin(deltaLng / 2);
  const value = sinLat * sinLat + Math.cos(startLat) * Math.cos(endLat) * sinLng * sinLng;
  return 2 * earthRadius * Math.atan2(Math.sqrt(value), Math.sqrt(1 - value));
}

function isPointInsideMapShape(point: Point, shape: RegionShape | null) {
  if (!shape) return true;
  if (shape.type === 'circle') {
    return getDistanceMetersBetweenPoints(point, shape.center) <= shape.radius;
  }
  return shape.points.length >= 3 && isPointInsidePolygon(point, shape.points);
}

function getMapShapeBounds(shape: RegionShape) {
  if (shape.type === 'circle') {
    const latRadius = shape.radius / 111320;
    const lngRadius = shape.radius / (111320 * Math.max(Math.cos((shape.center.y * Math.PI) / 180), 0.01));
    return {
      minLng: shape.center.x - lngRadius,
      minLat: shape.center.y - latRadius,
      maxLng: shape.center.x + lngRadius,
      maxLat: shape.center.y + latRadius,
    };
  }
  const lngs = shape.points.map((point) => point.x);
  const lats = shape.points.map((point) => point.y);
  return {
    minLng: Math.min(...lngs),
    minLat: Math.min(...lats),
    maxLng: Math.max(...lngs),
    maxLat: Math.max(...lats),
  };
}

function buildCirclePolygonPath(center: Point, radiusMeters: number, segments = 96): [number, number][][] {
  const lngRadius = radiusMeters / (111320 * Math.max(Math.cos((center.y * Math.PI) / 180), 0.01));
  const latRadius = radiusMeters / 111320;
  const ring: [number, number][] = [];
  for (let index = 0; index < segments; index += 1) {
    const angle = (index / segments) * Math.PI * 2;
    ring.push([
      center.x + Math.cos(angle) * lngRadius,
      center.y + Math.sin(angle) * latRadius,
    ]);
  }
  return [ring];
}

function getCircleRadiusLngLatOffset(center: Point, radiusMeters: number) {
  return {
    lng: radiusMeters / (111320 * Math.max(Math.cos((center.y * Math.PI) / 180), 0.01)),
    lat: radiusMeters / 111320,
  };
}

function countBy<T>(items: T[], getKey: (item: T) => unknown) {
  const counts = new Map<string, number>();
  for (const item of items) {
    const key = String(getKey(item) || '未分类').trim() || '未分类';
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  return Array.from(counts.entries()).sort((left, right) => right[1] - left[1] || left[0].localeCompare(right[0], 'zh-CN'));
}

function buildCountTable(title: string, label: string, rows: Array<[string, number]>) {
  const body = rows.length > 0
    ? rows.map(([name, count]) => `- ${label}：${name}，数量：${count}`).join('\n')
    : `- ${label}：无数据，数量：0`;
  return `${title}\n${body}`;
}

function normalizeMapStatsText(value: string) {
  return value
    .toLowerCase()
    .replace(/\s+/g, '')
    .replace(/[，。！？；：、,.!?;:()[\]{}"'`~@#$%^&*_+=<>|\\/]/g, '');
}

function extractMapStatsKeyword(question: string) {
  return normalizeMapStatsText(question)
    .replace(/(请问|帮我|麻烦|一下|其中|当前|这个|这个范围|圈选范围|范围内|圈内|区域内|地图内|统计|分析|查看|查询|识别|一下子)/g, '')
    .replace(/(poi|兴趣点|企业|公司|产业|工商|经营主体|数据)/g, '')
    .replace(/(有几个|有几家|有多少家|有多少个|有多少|几个|几家|多少家|多少个|多少|总数|总量|数量|一共|总共|合计|分别|其中有|有没有|有无)/g, '')
    .replace(/(大类|中类|小类|类别|分类|构成|情况|分布|占比|吗|呢|呀|吧|个|家|类|的|内|里)/g, '')
    .trim();
}

function isLikelyMapStatisticsQuestion(question: string) {
  if (/产业链|上下游|产业关联|产业集聚|产业集群|产业配套|关联产业|产业发展方向|适合发展|产业定位|招商方向|规划建议|发展建议|发展什么/.test(question)) {
    return false;
  }
  if (/poi|兴趣点|企业|公司|产业|工商|经营主体|网点|门店|设施|超市|便利店|药店|餐饮|酒店|医院|学校/i.test(question)) {
    return true;
  }
  if (/(有几个|有几家|有多少家|有多少个|有多少|几个|几家|多少家|多少个|多少|总数|总量|数量)/.test(question)) {
    return extractMapStatsKeyword(question).length > 0;
  }
  return /大类|中类|小类|类别|分类|构成|统计/.test(question);
}

const DISTRICT_NAMES = ['禅城区', '南海区', '顺德区', '三水区', '高明区', '禅城', '南海', '顺德', '三水', '高明'];

function extractDistrict(question: string): string | null {
  for (const name of DISTRICT_NAMES) {
    if (question.includes(name)) {
      return name.endsWith('区') ? name : name + '区';
    }
  }
  return null;
}

function isLikelyAreaCalculation(question: string): boolean {
  return /面积|用地面积|用地平衡|平衡表|用地构成|地类构成|地类平衡|圈选面积|计算面积|测算面积|统计面积|面积构成|面积占比|多大|多少平方米|多少公顷|多大面积/.test(question);
}

const INDUSTRY_KEYWORDS = [
  '新能源汽车', '汽车制造', '汽车零部件', '装备制造', '高端装备',
  '电子信息', '集成电路', '半导体', '光伏', '照明', '消费电子',
  '智能家居', '智能家电', '家电', '家具', '建材', '装饰材料',
  '新材料', '化工', '精细化工', '橡胶制品', '塑料制品', '金属制品',
  '生物医药', '医疗器械', '医药', '健康服务', '康养',
  '食品加工', '饮料食品', '食品制造', '酒类制造', '农副食品加工',
  '纺织服装', '服装鞋帽', '皮革毛皮', '羽毛制品',
  '商务服务', '金融服务', '现代物流', '物流仓储', '电子商务', '批发零售',
  '软件和信息技术服务', '信息技术服务', '软件服务', '互联网和相关服务',
  '研发设计', '科学技术服务', '专业技术服务',
  '文化旅游', '文创', '文化创意', '旅游服务', '酒店住宿', '餐饮',
  '房地产', '建筑工程', '土木工程', '建筑装饰',
  '现代农业', '智慧农业', '渔业', '水产养殖', '畜牧业', '种植业', '农产品加工',
  '节能环保', '资源循环', '环境治理', '新能源', '风能', '水能',
  '海洋经济', '海洋工程', '航空航天', '量子通信', '人工智能', '机器人',
];

const INDUSTRY_NEGATIVE_HINTS = ['产业', '企业', '公司', '经营主体', '区域', '地方', '本地', '园区', '上游', '下游', '产业链', '环节', '方向'];

function hasExplicitIndustry(question: string): boolean {
  const normalized = normalizeMapStatsText(question);
  if (!normalized) return false;

  for (const keyword of INDUSTRY_KEYWORDS) {
    const normalizedKeyword = normalizeMapStatsText(keyword);
    if (normalizedKeyword && normalized.includes(normalizedKeyword)) {
      return true;
    }
  }

  const syntaxMatch = normalized.match(/(.{2,8}?)产业|(.{2,8}?)行业|(.{2,8}?)(制造业|服务业|物流业|建筑业|金融业)/);
  if (syntaxMatch) {
    const candidate = (syntaxMatch[1] || syntaxMatch[2] || syntaxMatch[3] || '').trim();
    if (candidate && !INDUSTRY_NEGATIVE_HINTS.includes(candidate)) {
      return true;
    }
  }

  return false;
}

function asksIndustryJudgment(question: string): boolean {
  return /是否适合|适合不适合|适不适合|是否具备条件|具备条件|具备基础|是否有基础|有没有基础|招商条件|发展条件|发展前景|产业基础|是否可行|可行性|能不能发展|值不值得|是否有条件|有没有条件/.test(question);
}

function asksIndustryDirection(question: string): boolean {
  return /适合发展什么|应该发展什么|发展什么产业|产业发展方向|区域产业方向|招商方向|产业定位|主导产业|重点产业|推荐产业|优先发展|产业布局建议|发展建议|招商建议|应该招什么|适合招什么/.test(question);
}

type IndustryTaskHint = '企业统计' | '产业发展方向分析' | '企业关联分析';

function resolveIndustryTaskHint(question: string): IndustryTaskHint {
  const isStats = isLikelyMapStatisticsQuestion(question);
  const isJudgment = asksIndustryJudgment(question);
  const isDirection = asksIndustryDirection(question);
  const hasIndustry = hasExplicitIndustry(question);

  if (isStats && !isJudgment && !isDirection) return '企业统计';
  if (hasIndustry && isJudgment) return '企业关联分析';
  if (!hasIndustry && isDirection) return '产业发展方向分析';
  return '企业关联分析';
}

function findBestMapStatsMatch(
  question: string,
  candidates: Array<{ label: string; count: number; level: string }>,
) {
  const keyword = extractMapStatsKeyword(question);
  if (!keyword) return null;
  const normalizedKeyword = normalizeMapStatsText(keyword);
  const filtered = candidates.filter((candidate) => {
    const normalizedLabel = normalizeMapStatsText(candidate.label);
    return normalizedLabel && normalizedLabel !== '未分类'
      && (normalizedLabel.includes(normalizedKeyword) || normalizedKeyword.includes(normalizedLabel));
  });
  if (filtered.length === 0) return null;
  return filtered.sort((left, right) => {
    const leftLabel = normalizeMapStatsText(left.label);
    const rightLabel = normalizeMapStatsText(right.label);
    const leftExact = leftLabel === normalizedKeyword ? 1 : 0;
    const rightExact = rightLabel === normalizedKeyword ? 1 : 0;
    const levelWeight = (value: string) => (value === '小类' ? 3 : value === '中类' ? 2 : value === '大类' ? 1 : 0);
    return rightExact - leftExact
      || levelWeight(right.level) - levelWeight(left.level)
      || rightLabel.length - leftLabel.length
      || right.count - left.count;
  })[0];
}

function normalizeMapPath(path: unknown): Point[] {
  if (!Array.isArray(path) || path.length === 0) return [];
  const first = path[0];
  const firstIsCoordinatePair = Array.isArray(first)
    && first.length >= 2
    && Number.isFinite(Number(first[0]))
    && Number.isFinite(Number(first[1]));
  const source = Array.isArray(first) && !firstIsCoordinatePair && !('lng' in Object(first)) ? first : path;
  if (!Array.isArray(source)) return [];
  return source.flatMap((item) => {
    if (Array.isArray(item) && item.length >= 2 && Number.isFinite(item[0]) && Number.isFinite(item[1])) {
      return [{ x: Number(item[0]), y: Number(item[1]) }];
    }
    if (typeof item === 'object' && item !== null && 'lng' in item && 'lat' in item) {
      const candidate = item as { lng: number; lat: number };
      return Number.isFinite(candidate.lng) && Number.isFinite(candidate.lat)
        ? [{ x: candidate.lng, y: candidate.lat }]
        : [];
    }
    if (
      typeof item === 'object'
      && item !== null
      && 'getLng' in item
      && 'getLat' in item
      && typeof (item as { getLng?: unknown }).getLng === 'function'
      && typeof (item as { getLat?: unknown }).getLat === 'function'
    ) {
      const candidate = item as { getLng: () => number; getLat: () => number };
      const lng = Number(candidate.getLng());
      const lat = Number(candidate.getLat());
      return Number.isFinite(lng) && Number.isFinite(lat) ? [{ x: lng, y: lat }] : [];
    }
    return [];
  });
}

function escapeHtml(value: unknown) {
  const text = String(value ?? '—');
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function formatMetricValue(value: unknown, digits = 2) {
  const num = Number(value);
  if (!Number.isFinite(num)) return '—';
  return num.toLocaleString('zh-CN', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function extractAreaTable(toolResults: Record<string, unknown> | undefined): RenderTable | null {
  const areaCalculation = toolResults?.area_calculation as Record<string, unknown> | undefined;
  if (!areaCalculation) return null;
  const areas = areaCalculation.areas as Record<string, Record<string, unknown>> | undefined;
  const summary = areaCalculation.summary as Record<string, unknown> | undefined;
  if (!areas || Object.keys(areas).length === 0) return null;
  const matchedHectares = Number(summary?.visible_matched_hectares ?? summary?.matched_hectares ?? 0);
  const rows = Object.entries(areas)
    .map(([landType, metrics], index) => {
      const hectares = Number(metrics.hectares ?? 0);
      const ratio = matchedHectares > 0 ? (hectares / matchedHectares) * 100 : 0;
      return [
        String(index + 1),
        landType,
        formatMetricValue(metrics.pixels, 0),
        formatMetricValue(metrics.square_meters, 2),
        formatMetricValue(metrics.hectares, 4),
        formatMetricValue(ratio, 2),
      ];
    })
    .sort((a, b) => Number(b[4].replace(/,/g, '')) - Number(a[4].replace(/,/g, '')));
  const footnote = summary
    ? `匹配面积 ${formatMetricValue(summary.visible_matched_square_meters ?? summary.matched_square_meters, 2)} 平方米 / ${formatMetricValue(summary.visible_matched_hectares ?? summary.matched_hectares, 4)} 公顷，未匹配 ${formatMetricValue(summary.unmatched_hectares, 4)} 公顷`
    : undefined;
  return {
    title: '圈选区域用地构成',
    headers: ['序号', '用地分类', '像素数', '面积(平方米)', '面积(公顷)', '占匹配面积比(%)'],
    rows,
    footnote,
  };
}

function extractMarkdownTable(content: string): { before: string; table: RenderTable; after: string } | null {
  const lines = content.split('\n');
  let start = -1;
  for (let i = 0; i < lines.length - 1; i += 1) {
    if (lines[i].includes('|') && /^\s*\|?[-:\s|]+\|?\s*$/.test(lines[i + 1])) {
      start = i;
      break;
    }
  }
  if (start === -1) return null;
  let end = start + 2;
  while (end < lines.length && lines[end].includes('|')) end += 1;
  const headerLine = lines[start];
  const rowLines = lines.slice(start + 2, end);
  const splitRow = (line: string) => line.split('|').map((cell) => cell.trim()).filter((cell, index, arr) => !(cell === '' && (index === 0 || index === arr.length - 1)));
  const headers = splitRow(headerLine);
  const rows = rowLines.map(splitRow).filter((row) => row.length === headers.length);
  if (headers.length === 0 || rows.length === 0) return null;
  return {
    before: lines.slice(0, start).join('\n').trim(),
    table: { headers, rows },
    after: lines.slice(end).join('\n').trim(),
  };
}

function ResponseTable({ table }: { table: RenderTable }) {
  return (
    <div className="response-table-card">
      {table.title && <div className="response-table-title">{table.title}</div>}
      <div className="response-table-wrap">
        <table className="response-table">
          <thead>
            <tr>
              {table.headers.map((header) => <th key={header}>{header}</th>)}
            </tr>
          </thead>
          <tbody>
            {table.rows.map((row, index) => (
              <tr key={`${row[0]}-${index}`}>
                {row.map((cell, cellIndex) => <td key={`${cellIndex}-${cell}`}>{cell}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {table.footnote && <div className="response-table-footnote">{table.footnote}</div>}
    </div>
  );
}

function AssistantMessageBody({ message }: { message: ChatMessage }) {
  const meta = (message.meta ?? {}) as Record<string, unknown>;
  const structuredTable = extractAreaTable(meta.tool_results as Record<string, unknown> | undefined);
  const markdownTable = structuredTable ? null : extractMarkdownTable(message.content);
  const plainText = markdownTable ? [markdownTable.before, markdownTable.after].filter(Boolean).join('\n\n') : message.content;

  return (
    <>
      {plainText && <div className="bubble rich-bubble">{plainText}</div>}
      {structuredTable && <ResponseTable table={structuredTable} />}
      {!structuredTable && markdownTable && <ResponseTable table={markdownTable.table} />}
      {message.meta && <details><summary>工具与调试</summary><pre>{JSON.stringify(message.meta, null, 2)}</pre></details>}
    </>
  );
}

function ThinkingPanel({ steps }: { steps: { label: string; detail: string }[] }) {
  return (
    <div className="thinking-panel">
      <div className="thinking-title">规划分析思考中</div>
      <div className="thinking-subtitle">正在结合圈选区域、图例和规划问题组织结果</div>
      <div className="thinking-step-list">
        {steps.map((step, index) => (
          <div key={step.label} className="thinking-step">
            <span className="thinking-step-index">{index + 1}</span>
            <div>
              <strong>{step.label}</strong>
              <p>{step.detail}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function clampCircleRadius(radius: number) {
  if (!Number.isFinite(radius)) return 0;
  return Math.max(0, radius);
}

function getLegendCalibrationMethodLabel(method: unknown) {
  switch (String(method ?? '')) {
    case 'legend_panel_grid':
      return '图例框色块提取';
    case 'legend_swatches':
      return '图例色块匹配';
    default:
      return '全图颜色校准';
  }
}

function getLegendSourceLabel(source: unknown) {
  switch (String(source ?? '')) {
    case 'legend_panel_grid':
      return '图例框';
    case 'legend_swatches':
      return '图例色块';
    case 'global_palette':
      return '全图';
    default:
      return '未知来源';
  }
}

function LegendPanel({
  legend,
  scale,
  onRecalibrate,
  calibrating,
  calibrationMessage,
}: {
  legend: Record<string, string>;
  scale: Record<string, unknown>;
  onRecalibrate: () => Promise<void>;
  calibrating: boolean;
  calibrationMessage: string;
}) {
  const entries = Object.entries(legend);
  const calibrationDebug = (scale.legend_calibration_debug ?? null) as Record<string, unknown> | null;
  const calibrationSummary = (calibrationDebug?.summary ?? null) as Record<string, unknown> | null;
  const panelGrid = (calibrationDebug?.panel_grid ?? null) as Record<string, unknown> | null;
  const gridSwatches = Array.isArray(panelGrid?.grid_swatches)
    ? (panelGrid?.grid_swatches as Array<Record<string, unknown>>)
    : [];
  const legendItems = Array.isArray(calibrationDebug?.legend_items)
    ? (calibrationDebug?.legend_items as Array<Record<string, unknown>>)
    : [];
  const legendItemMap = new Map<string, Record<string, unknown>>();
  legendItems.forEach((item) => {
    const landType = item.land_type;
    if (typeof landType === 'string') legendItemMap.set(landType, item);
  });
  if (entries.length === 0) return <div className="muted-card">暂无图例，请先上传并完成识别。</div>;
  return (
    <>
      <div className="legend-actions">
        <button className="ghost-btn section-btn" onClick={() => void onRecalibrate()} disabled={calibrating}>
          {calibrating ? '校准中...' : '重新校准图例'}
        </button>
      </div>
      {calibrationMessage && <div className="scale-calibration-success">{calibrationMessage}</div>}
      {calibrationSummary && (
        <div className="legend-calibration-card">
          <div className="legend-calibration-head">
            <strong>当前提色</strong>
            <span className="legend-calibration-method">{getLegendCalibrationMethodLabel(calibrationSummary.method)}</span>
          </div>
          <div className="legend-calibration-meta">
            <span>已校准 {formatMetricValue(calibrationSummary.matched_item_count, 0)} / {formatMetricValue(calibrationSummary.item_count, 0)} 项</span>
            {gridSwatches.length > 0 && <span>抽取色块 {formatMetricValue(gridSwatches.length, 0)} 个</span>}
          </div>
          {gridSwatches.length > 0 && (
            <div className="legend-swatch-grid-preview">
              {gridSwatches.map((swatch, index) => (
                <div
                  key={`${swatch.column}-${swatch.row}-${swatch.color}-${index}`}
                  className="legend-swatch-grid-item"
                  title={`列 ${Number(swatch.column) + 1} 行 ${Number(swatch.row) + 1} ${String(swatch.color ?? '')}`}
                >
                  <span className="legend-swatch-grid-color" style={{ backgroundColor: String(swatch.color ?? '#000000') }} />
                  <span className="legend-swatch-grid-index">{Number(swatch.column) + 1}-{Number(swatch.row) + 1}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
      <div className="legend-grid compact">
        {entries.map(([landType, color]) => {
          const itemMeta = legendItemMap.get(landType);
          const gridPosition = itemMeta?.grid_position as Record<string, unknown> | undefined;
          return (
            <div className="legend-row" key={landType} title={`${landType} ${color}`}>
              <span className="legend-swatch" style={{ backgroundColor: color }} />
              <div className="legend-row-body">
                <span className="legend-label">{landType}</span>
                {itemMeta && (
                  <span className="legend-row-meta">
                    {getLegendSourceLabel(itemMeta.source)}
                    {gridPosition && <> · {Number(gridPosition.column) + 1}-{Number(gridPosition.row) + 1}</>}
                  </span>
                )}
              </div>
              <span className="legend-hex">{color}</span>
            </div>
          );
        })}
      </div>
    </>
  );
}

function ScalePanel({
  scale,
  onCalibrate,
  calibrating,
  calibrationMessage,
}: {
  scale: Record<string, unknown>;
  onCalibrate: (payload: {
    metersPerPixel?: number;
    referenceDistanceMeters?: number;
    referencePixelLength?: number;
    scaleText?: string;
  }) => Promise<void>;
  calibrating: boolean;
  calibrationMessage: string;
}) {
  const detection = scale.scale_detection as Record<string, unknown> | undefined;
  const calibration = scale.legend_calibration_status as Record<string, unknown> | undefined;
  const manualCalibration = scale.manual_calibration as Record<string, unknown> | undefined;
  const [showCalibrationForm, setShowCalibrationForm] = useState(false);
  const [metersPerPixelInput, setMetersPerPixelInput] = useState(scale.meters_per_pixel ? String(scale.meters_per_pixel) : '');
  const [referenceDistanceInput, setReferenceDistanceInput] = useState('');
  const [referencePixelInput, setReferencePixelInput] = useState(detection?.pixel_length ? String(detection.pixel_length) : '');
  const [scaleTextInput, setScaleTextInput] = useState(scale.scale_text ? String(scale.scale_text) : '');

  useEffect(() => {
    setMetersPerPixelInput(scale.meters_per_pixel ? String(scale.meters_per_pixel) : '');
    setReferencePixelInput(detection?.pixel_length ? String(detection.pixel_length) : '');
    setScaleTextInput(scale.scale_text ? String(scale.scale_text) : '');
  }, [scale, detection?.pixel_length]);

  async function handleSubmitCalibration() {
    const metersPerPixel = Number(metersPerPixelInput);
    const referenceDistanceMeters = Number(referenceDistanceInput);
    const referencePixelLength = Number(referencePixelInput);
    await onCalibrate(
      Number.isFinite(metersPerPixel) && metersPerPixel > 0
        ? {
            metersPerPixel,
            scaleText: scaleTextInput.trim() || undefined,
          }
        : {
            referenceDistanceMeters,
            referencePixelLength,
            scaleText: scaleTextInput.trim() || undefined,
          },
    );
    setReferenceDistanceInput('');
    setShowCalibrationForm(false);
  }

  return (
    <div className="scale-card compact">
      <div className="scale-main">
        <span>1 px</span>
        <strong>{formatNumber(scale.meters_per_pixel)} m</strong>
      </div>
      <div className="scale-bar"><span /><span /><span /></div>
      <div className="scale-labels">
        <span>0</span>
        <span>{scale.scale_text ? String(scale.scale_text) : '比例尺未识别'}</span>
      </div>
      <div className="scale-meta">
        <div><b>检测</b><span>{detection?.status ? String(detection.status) : '—'}</span></div>
        <div><b>标尺</b><span>{detection?.pixel_length ? `${detection.pixel_length}px` : '—'}</span></div>
        <div><b>图例</b><span>{calibration?.enabled ? `已校准 ${calibration.items ?? 0} 项` : '未校准'}</span></div>
        <div><b>校正</b><span>{manualCalibration?.enabled ? '已手动校正' : '未手动校正'}</span></div>
      </div>
      <div className="scale-actions">
        <button className="ghost-btn section-btn" onClick={() => setShowCalibrationForm((value) => !value)}>
          {showCalibrationForm ? '收起校正' : '手动校正'}
        </button>
      </div>
      {calibrationMessage && <div className="scale-calibration-success">{calibrationMessage}</div>}
      {showCalibrationForm && (
        <div className="scale-calibration-form">
          <label className="scale-calibration-field">
            <span>直接输入 1px 对应米数</span>
            <input value={metersPerPixelInput} onChange={(event) => setMetersPerPixelInput(event.target.value)} placeholder="如 0.5" />
          </label>
          <div className="scale-calibration-divider">或按参考距离换算</div>
          <div className="scale-calibration-grid">
            <label className="scale-calibration-field">
              <span>参考距离(米)</span>
              <input value={referenceDistanceInput} onChange={(event) => setReferenceDistanceInput(event.target.value)} placeholder="如 500" />
            </label>
            <label className="scale-calibration-field">
              <span>对应像素长度(px)</span>
              <input value={referencePixelInput} onChange={(event) => setReferencePixelInput(event.target.value)} placeholder="如 248" />
            </label>
          </div>
          <label className="scale-calibration-field">
            <span>比例尺文字</span>
            <input value={scaleTextInput} onChange={(event) => setScaleTextInput(event.target.value)} placeholder="如 0 500m 1000m" />
          </label>
          <button className="ask-btn" onClick={() => void handleSubmitCalibration()} disabled={calibrating}>
            {calibrating ? '保存中...' : '保存校正'}
          </button>
        </div>
      )}
    </div>
  );
}

function DiagramLibrary({
  diagrams,
  selectedId,
  onSelect,
  onUpload,
  collapsed,
  onToggle,
  onRename,
  onDelete,
}: {
  diagrams: Diagram[];
  selectedId: number | null;
  onSelect: (id: number) => void;
  onUpload: (event: ChangeEvent<HTMLInputElement>) => void;
  collapsed: boolean;
  onToggle: () => void;
  onRename: (diagram: Diagram) => Promise<void>;
  onDelete: (diagram: Diagram) => Promise<void>;
}) {
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editingName, setEditingName] = useState('');

  const startRename = (diagram: Diagram) => {
    setEditingId(diagram.id);
    setEditingName(diagram.filename);
  };

  const commitRename = (diagram: Diagram) => {
    setEditingId(null);
    if (editingName.trim() && editingName.trim() !== diagram.filename) {
      diagram.filename = editingName.trim();
      void onRename(diagram);
    }
  };

  return (
    <aside className={collapsed ? 'library-panel collapsed' : 'library-panel'}>
      <div className="panel-head">
        {!collapsed && <div><h2>图纸库</h2><p>{diagrams.length} 张图纸</p></div>}
        <div className="panel-actions">
          <button className="icon-btn" onClick={onToggle}>{collapsed ? '展开' : '收起'}</button>
        </div>
      </div>
      {collapsed ? (
        <div className="vertical-label">图纸</div>
      ) : (
        <>
          <label className="upload-zone">
            <span>上传图纸</span>
            <small>JPG / PNG</small>
            <input type="file" accept=".jpg,.jpeg,.png" onChange={onUpload} />
          </label>
          <div className="diagram-list">
            {diagrams.map((diagram) => (
              <div key={diagram.id} className={diagram.id === selectedId ? 'diagram-card active' : 'diagram-card'}>
                <div className="diagram-card-main" onClick={() => onSelect(diagram.id)}>
                  {editingId === diagram.id ? (
                    <input
                      className="diagram-rename-input"
                      value={editingName}
                      onChange={(e) => setEditingName(e.target.value)}
                      onBlur={() => commitRename(diagram)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') commitRename(diagram);
                        if (e.key === 'Escape') setEditingId(null);
                      }}
                      onClick={(e) => e.stopPropagation()}
                      autoFocus
                    />
                  ) : (
                    <span className="diagram-name" onDoubleClick={() => startRename(diagram)}>{diagram.filename}</span>
                  )}
                </div>
                <button className="diagram-delete-btn" onClick={() => void onDelete(diagram)} title="删除">×</button>
              </div>
            ))}
            {diagrams.length === 0 && <div className="muted-card">暂无图纸。</div>}
          </div>
        </>
      )}
    </aside>
  );
}

function ChatPanel({
  messages,
  question,
  chatMode,
  imageAttachment,
  loading,
  disabled,
  onQuestionChange,
  onChatModeChange,
  onPickImage,
  onClearImage,
  onAsk,
  onStop,
  onClear,
  onResetSize,
  thinkingSteps,
}: {
  messages: ChatMessage[];
  question: string;
  chatMode: ChatMode;
  imageAttachment: ChatImageAttachment | null;
  loading: boolean;
  disabled: boolean;
  onQuestionChange: (value: string) => void;
  onChatModeChange: (value: ChatMode) => void;
  onPickImage: (event: ChangeEvent<HTMLInputElement>) => void;
  onClearImage: () => void;
  onAsk: () => void;
  onStop: () => void;
  onClear: () => void;
  onResetSize: () => void;
  thinkingSteps: { label: string; detail: string }[];
}) {
  return (
    <aside className="chat-panel">
      <div className="panel-head">
        <div><h2>规划对话</h2><p>支持连续追问，工具结果自动附带</p></div>
        <div className="panel-actions">
          <button className="ghost-btn" onClick={onResetSize}>恢复宽度</button>
          <button className="ghost-btn" onClick={onClear}>清空</button>
        </div>
      </div>
      <div className="chat-history">
        {messages.length === 0 && (
        <div className="chat-empty">
          <strong>开始一次区域分析</strong>
          <span>选择数据分析、知识库问答或企业关联后直接提问。</span>
        </div>
      )}
        {messages.map((message) => (
          <div key={message.id} className={`chat-message ${message.role}`}>
            {message.role === 'assistant' ? <AssistantMessageBody message={message} /> : <div className="bubble">{message.content}</div>}
          </div>
        ))}
        {loading && (
          <div className="chat-message assistant">
            <ThinkingPanel steps={thinkingSteps} />
          </div>
        )}
      </div>
      <div className="chat-composer">
        <div className="chat-control-row">
          <div className="chat-mode-tabs">
            {CHAT_MODE_ORDER.map((mode) => (
              <button
                key={mode}
                className={`chat-mode-tab ${chatMode === mode ? 'active' : ''}`}
                onClick={() => onChatModeChange(mode)}
              >
                {CHAT_MODE_CONFIG[mode].icon} {CHAT_MODE_CONFIG[mode].label}
              </button>
            ))}
          </div>
          <label className="ghost-btn chat-upload-btn">
            上传图片
            <input type="file" accept=".png,.jpg,.jpeg" onChange={onPickImage} />
          </label>
        </div>
        <div className="chat-upload-row">
          {imageAttachment && (
            <div className="chat-upload-chip">
              <span title={imageAttachment.name}>{imageAttachment.name}</span>
              <button className="ghost-btn section-btn" onClick={onClearImage}>移除</button>
            </div>
          )}
        </div>
        <textarea
          value={question}
          onChange={(event) => onQuestionChange(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.shiftKey) {
              event.preventDefault();
              if (!loading && !disabled) onAsk();
            }
          }}
          placeholder="输入你的问题，可附带 jpg/png 图片一起分析..."
          rows={4}
        />
        <div className="ask-actions-row">
          <button className="ask-btn" onClick={onAsk} disabled={loading || disabled}>{loading ? '分析中...' : '发送'}</button>
          {loading && <button className="stop-btn" onClick={onStop}>停止分析</button>}
        </div>
      </div>
    </aside>
  );
}

export default function App() {
  const [diagrams, setDiagrams] = useState<Diagram[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [libraryCollapsed, setLibraryCollapsed] = useState(false);
  const [libraryWidth, setLibraryWidth] = useState(() => readStoredSize(STORAGE_KEYS.libraryWidth, LIBRARY_WIDTH_RANGE.default, LIBRARY_WIDTH_RANGE.min, LIBRARY_WIDTH_RANGE.max));
  const [chatWidth, setChatWidth] = useState(() => readStoredSize(STORAGE_KEYS.chatWidth, CHAT_WIDTH_RANGE.default, CHAT_WIDTH_RANGE.min, CHAT_WIDTH_RANGE.max));
  const [companyDrawerWidth, setCompanyDrawerWidth] = useState(() => readStoredSize(STORAGE_KEYS.companyDrawerWidth, COMPANY_DRAWER_WIDTH_RANGE.default, COMPANY_DRAWER_WIDTH_RANGE.min, COMPANY_DRAWER_WIDTH_RANGE.max));
  const [belowInfoHeight, setBelowInfoHeight] = useState(() => readStoredSize(STORAGE_KEYS.belowInfoHeight, BELOW_INFO_HEIGHT_RANGE.default, BELOW_INFO_HEIGHT_RANGE.min, BELOW_INFO_HEIGHT_RANGE.max));
  const [belowInfoCollapsed, setBelowInfoCollapsed] = useState(true);
  const [dragHint, setDragHint] = useState<{ label: string; value: number; unit: string; x: number; y: number } | null>(null);
  const [question, setQuestion] = useState('');
  const [chatMode, setChatMode] = useState<ChatMode>(() => {
    if (typeof window === 'undefined') return 'analysis';
    return normalizeStoredChatMode(window.localStorage.getItem(STORAGE_KEYS.taskHint));
  });
  const [chatImageAttachment, setChatImageAttachment] = useState<ChatImageAttachment | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [conversationMap, setConversationMap] = useState<Record<string, string>>(() => {
    if (typeof window === 'undefined') return {};
    try {
      const raw = window.localStorage.getItem(STORAGE_KEYS.conversationMap);
      return raw ? JSON.parse(raw) as Record<string, string> : {};
    } catch {
      return {};
    }
  });
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [thinkingSteps, setThinkingSteps] = useState<{ label: string; detail: string }[]>([]);
  const [mode, setMode] = useState<'polygon' | 'circle' | 'rectangle'>('polygon');
  const [points, setPoints] = useState<Point[]>([]);
  const [circle, setCircle] = useState<{ center: Point; radius: number } | null>(null);
  const [rectangle, setRectangle] = useState<{ start: Point; end: Point } | null>(null);
  const [mapShape, setMapShape] = useState<RegionShape | null>(null);
  const [draggingRectangle, setDraggingRectangle] = useState(false);
  const [circleHandleAngle, setCircleHandleAngle] = useState(0);
  const [circleRadiusImageInput, setCircleRadiusImageInput] = useState('');
  const [circleRadiusMetersInput, setCircleRadiusMetersInput] = useState('');
  const [editingCircleRadiusField, setEditingCircleRadiusField] = useState<'image' | 'meters' | null>(null);
  const [draggingCircle, setDraggingCircle] = useState(false);
  const [circleDragMode, setCircleDragMode] = useState<'create' | 'move-center' | 'resize' | null>(null);
  const [mapCircleDrawingEnabled, setMapCircleDrawingEnabled] = useState(false);
  const [mapCircleRadiusKmInput, setMapCircleRadiusKmInput] = useState('');
  const [editingMapCircleRadius, setEditingMapCircleRadius] = useState(false);
  const [dragOffset, setDragOffset] = useState<Point | null>(null);
  const [panningDiagram, setPanningDiagram] = useState(false);
  const requestAbortRef = useRef<AbortController | null>(null);
  const overlayRef = useRef<SVGSVGElement | null>(null);
  const diagramViewportRef = useRef<HTMLDivElement | null>(null);
  const diagramPanRef = useRef<{ startX: number; startY: number; scrollLeft: number; scrollTop: number } | null>(null);
  const amapContainerRef = useRef<HTMLDivElement | null>(null);
  const amapInstanceRef = useRef<AMapInstance | null>(null);
  const mapMouseToolRef = useRef<AMapMouseTool | null>(null);
  const mapDrawOverlayRef = useRef<AMapPolygon | AMapCircle | null>(null);
  const mapGuideOverlayRefs = useRef<AMapOverlayLike[]>([]);
  const workspaceRef = useRef<HTMLElement | null>(null);
  const mapWorkbenchRef = useRef<HTMLElement | null>(null);
  const workbenchMainRef = useRef<HTMLDivElement | null>(null);
  const [diagramViewportSize, setDiagramViewportSize] = useState({ width: 1, height: 1 });
  const [viewerZoom, setViewerZoom] = useState(1);
  const [showDiagramLayer, setShowDiagramLayer] = useState(false);
  const [mapLayerMode, setMapLayerMode] = useState<'roadmap' | 'satellite' | null>('roadmap');
  const [showCompanyLayer, setShowCompanyLayer] = useState(false);
  const [showPoiLayer, setShowPoiLayer] = useState(false);
  const [showLandUseLayer, setShowLandUseLayer] = useState(false);
  const [amapSdkReady, setAmapSdkReady] = useState(() => (typeof window !== 'undefined' ? Boolean(window.AMap) : false));
  const [mapSearchQuery, setMapSearchQuery] = useState('');
  const [mapSearching, setMapSearching] = useState(false);
  const [scaleCalibrating, setScaleCalibrating] = useState(false);
  const [scaleCalibrationMessage, setScaleCalibrationMessage] = useState('');
  const [legendCalibrating, setLegendCalibrating] = useState(false);
  const [legendCalibrationMessage, setLegendCalibrationMessage] = useState('');
  const [companyKeyword, setCompanyKeyword] = useState('');
  const [companyDistrict, setCompanyDistrict] = useState<(typeof COMPANY_DISTRICTS)[number]>('全部');
  const [visibleCompanies, setVisibleCompanies] = useState<CompanyPoint[]>([]);
  const [visiblePois, setVisiblePois] = useState<PoiPoint[]>([]);
  const [poiCategories, setPoiCategories] = useState<PoiCategory[]>([]);
  const [enabledPoiCategories, setEnabledPoiCategories] = useState<string[]>([]);
  const [selectedCompanyId, setSelectedCompanyId] = useState<number | null>(null);
  const [selectedCompanyDetail, setSelectedCompanyDetail] = useState<CompanyDetail | null>(null);
  const [showCompanyPanel, setShowCompanyPanel] = useState(true);
  const companyInfoWindowRef = useRef<{ open?: (map: unknown, position: [number, number]) => void; close?: () => void } | null>(null);
  const poiInfoWindowRef = useRef<{ open?: (map: unknown, position: [number, number]) => void; close?: () => void } | null>(null);
  const landUseInfoWindowRef = useRef<{ open?: (map: unknown, position: [number, number]) => void; close?: () => void } | null>(null);
  const companyDetailCacheRef = useRef(new Map<number, CompanyDetail>());
  const landUseDatasetRef = useRef<LandUseDataset | null>(null);
  const companyRequestIdRef = useRef(0);
  const poiRequestIdRef = useRef(0);
  const companyRenderTimerRef = useRef<number | null>(null);
  const poiRenderTimerRef = useRef<number | null>(null);
  const companyMarkerMapRef = useRef(new Map<number, AMapMarker>());
  const poiMarkerMapRef = useRef(new Map<number, AMapMarker>());
  const companyRelationMapRef = useRef(new Map<number, string>());
  const [showRelationLegend, setShowRelationLegend] = useState(false);
  const [layerSubOpen, setLayerSubOpen] = useState<Set<'company' | 'poi'>>(new Set());
  const toggleLayerSub = (key: 'company' | 'poi') => {
    setLayerSubOpen((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };
  const RELATION_COLORS: Record<string, string> = { target: '#ef4444', upstream: '#22c55e', downstream: '#f97316', other: '#3b82f6' };
  const RELATION_LABELS: Record<string, string> = { other: '普通企业', target: '目标产业企业', upstream: '上游关联企业', downstream: '下游关联企业' };
  const RELATION_ORDER: Array<keyof typeof RELATION_LABELS> = ['other', 'target', 'upstream', 'downstream'];
  const DEFAULT_MARKER_COLOR = '#3b82f6';
  const [companyCategoryVisible, setCompanyCategoryVisible] = useState<Set<string>>(new Set(RELATION_ORDER));
  const toggleCompanyCategory = (key: string) => {
    setCompanyCategoryVisible((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };
  const landUsePolygonMapRef = useRef(new Map<number, AMapPolygon>());
  const hoveredLandUseFeatureRef = useRef<number | null>(null);
  const selectedLandUseFeatureRef = useRef<number | null>(null);
  const mapViewRef = useRef<{ center: [number, number]; zoom: number }>(DEFAULT_MAP_VIEW);
  const pendingMapJumpRef = useRef<{ center: [number, number]; zoom: number } | null>(null);
  const mapReadyRef = useRef(false);
  const [companyLayerStatus, setCompanyLayerStatus] = useState<CompanyLayerStatus>({
    state: 'idle',
    message: '打开高德地图后加载企业图层',
  });

  const selectedDiagram = useMemo(() => diagrams.find((item) => item.id === selectedId) || null, [diagrams, selectedId]);
  const conversationMode = chatImageAttachment ? 'image' : 'text';
  const currentConversationKey = useMemo(
    () => getConversationStorageKey(selectedId, conversationMode, chatMode),
    [selectedId, conversationMode, chatMode],
  );
  const currentLegend = selectedDiagram?.legend_json || {};
  const currentScale = selectedDiagram?.scale_json || {};
  const showMapLayer = mapLayerMode !== null;
  const currentConversationId = currentConversationKey ? (conversationMap[currentConversationKey] ?? null) : null;
  const effectiveConversationId = messages.length > 0 ? currentConversationId : null;
  const displaySize = useMemo(() => fitDiagramSize(selectedDiagram, diagramViewportSize), [selectedDiagram, diagramViewportSize]);
  const zoomedCanvasSize = useMemo(() => ({
    width: displaySize.width * viewerZoom,
    height: displaySize.height * viewerZoom,
  }), [displaySize, viewerZoom]);
  const poiCategoryColorMap = useMemo(
    () => buildPoiCategoryColorMap(poiCategories.map((item) => item.name)),
    [poiCategories],
  );
  const overlayVisuals = useMemo(() => ({
    polygonStrokeWidth: 1.5 / viewerZoom,
    pointRadius: 3 / viewerZoom,
    circleStrokeWidth: 1.5 / viewerZoom,
    guideStrokeWidth: 1.5 / viewerZoom,
    guideDasharray: `${6 / viewerZoom} ${4 / viewerZoom}`,
    crosshairHalfSize: 8 / viewerZoom,
    handleRadius: 5.5 / viewerZoom,
    handleStrokeWidth: 1.5 / viewerZoom,
  }), [viewerZoom]);
  const rectanglePoints = useMemo(() => {
    if (!rectangle) return [];
    const minX = Math.min(rectangle.start.x, rectangle.end.x);
    const maxX = Math.max(rectangle.start.x, rectangle.end.x);
    const minY = Math.min(rectangle.start.y, rectangle.end.y);
    const maxY = Math.max(rectangle.start.y, rectangle.end.y);
    if (maxX - minX <= 0 || maxY - minY <= 0) return [];
    return [
      { x: minX, y: minY },
      { x: maxX, y: minY },
      { x: maxX, y: maxY },
      { x: minX, y: maxY },
    ];
  }, [rectangle]);
  const isMapShapeTarget = showMapLayer && !showDiagramLayer && (showCompanyLayer || showPoiLayer || showLandUseLayer);
  const hasDiagramShape = mode === 'polygon'
    ? points.length >= 3
    : mode === 'rectangle'
      ? rectanglePoints.length === 4
      : Boolean(circle && circle.radius > 0);
  const hasMapShape = mapShape !== null;
  const hasShape = hasDiagramShape || hasMapShape;
  const metersPerPixel = Number(currentScale.meters_per_pixel);
  const isMapCircleDrawingActive = isMapShapeTarget && mode === 'circle' && mapCircleDrawingEnabled;
  const isLandUseMapCircleEditorEnabled = showMapLayer && showLandUseLayer && isMapShapeTarget && mode === 'circle';
  const effectiveBelowInfoHeight = belowInfoCollapsed ? BELOW_INFO_HEIGHT_RANGE.collapsed : belowInfoHeight;
  const workspaceColumns = libraryCollapsed
    ? `56px 0px minmax(0,1fr) ${RESIZER_SIZE}px ${chatWidth}px`
    : `${libraryWidth}px ${RESIZER_SIZE}px minmax(0,1fr) ${RESIZER_SIZE}px ${chatWidth}px`;
  const workbenchColumns = showCompanyPanel && showMapLayer && showCompanyLayer
    ? `minmax(0,1fr) ${RESIZER_SIZE}px ${companyDrawerWidth}px`
    : 'minmax(0,1fr)';

  const circleMetrics = useMemo(() => {
    if (circle === null || selectedDiagram === null || displaySize.width <= 0 || displaySize.height <= 0) return null;
    const centerDisplay = imagePointToDisplayPoint(circle.center, displaySize, selectedDiagram);
    const radiusDisplayPx = imageRadiusToDisplayRadius(circle.radius, displaySize.width, selectedDiagram);
    const radiusImagePx = circle.radius;
    const radiusMeters = Number.isFinite(metersPerPixel) ? radiusImagePx * metersPerPixel : null;
    const handleX = centerDisplay.x + Math.cos(circleHandleAngle) * radiusDisplayPx;
    const handleY = centerDisplay.y + Math.sin(circleHandleAngle) * radiusDisplayPx;
    return {
      radiusDisplayPx,
      radiusImagePx,
      radiusMeters,
      center: centerDisplay,
      edge: { x: handleX, y: handleY },
      diameterMeters: radiusMeters === null ? null : radiusMeters * 2,
    };
  }, [circle, circleHandleAngle, displaySize, selectedDiagram, metersPerPixel]);
  const mapCircleMetrics = useMemo(() => {
    if (!isLandUseMapCircleEditorEnabled || mapShape?.type !== 'circle') return null;
    return {
      radiusKm: mapShape.radius / 1000,
      diameterKm: (mapShape.radius * 2) / 1000,
    };
  }, [isLandUseMapCircleEditorEnabled, mapShape]);
  function beginDrag(
    event: ReactMouseEvent<HTMLDivElement>,
    onMove: (moveEvent: MouseEvent) => void,
    onEnd?: () => void,
  ) {
    event.preventDefault();
    document.body.style.userSelect = 'none';
    const handleMove = (moveEvent: MouseEvent) => onMove(moveEvent);
    const handleUp = () => {
      document.body.style.userSelect = '';
      window.removeEventListener('mousemove', handleMove);
      window.removeEventListener('mouseup', handleUp);
      onEnd?.();
    };
    window.addEventListener('mousemove', handleMove);
    window.addEventListener('mouseup', handleUp);
  }

  useEffect(() => {
    listDiagrams().then((items) => {
      setDiagrams(items);
      if (items[0]) setSelectedId(items[0].id);
    }).catch((err) => setError(String(err.message || err)));
  }, []);

  useEffect(() => {
    if (amapSdkReady) return;
    let attempts = 0;
    const timer = window.setInterval(() => {
      if (window.AMap) {
        setAmapSdkReady(true);
        window.clearInterval(timer);
        return;
      }
      attempts += 1;
      if (attempts >= 40) {
        window.clearInterval(timer);
        setError((current) => current || '高德地图脚本加载失败，请刷新页面后重试。');
      }
    }, 250);
    return () => window.clearInterval(timer);
  }, [amapSdkReady]);

  useEffect(() => {
    const updateSize = () => {
      const rect = diagramViewportRef.current?.getBoundingClientRect();
      if (rect) setDiagramViewportSize({ width: rect.width, height: rect.height });
    };
    const frame = window.requestAnimationFrame(updateSize);
    const viewportElement = diagramViewportRef.current;
    const resizeObserver = typeof ResizeObserver !== 'undefined' && viewportElement
      ? new ResizeObserver(() => updateSize())
      : null;
    if (viewportElement && resizeObserver) {
      resizeObserver.observe(viewportElement);
    }
    window.addEventListener('resize', updateSize);
    return () => {
      window.cancelAnimationFrame(frame);
      resizeObserver?.disconnect();
      window.removeEventListener('resize', updateSize);
    };
  }, [selectedId, showDiagramLayer, showMapLayer, showCompanyPanel, showCompanyLayer, companyDrawerWidth, libraryWidth, chatWidth, libraryCollapsed]);

  useEffect(() => {
    if (!showMapLayer || !showCompanyLayer || !amapInstanceRef.current) return;
    const map = amapInstanceRef.current;
    companyMarkerMapRef.current.forEach((marker, id) => {
      const relation = companyRelationMapRef.current.get(id) ?? 'other';
      const visible = companyCategoryVisible.has(relation);
      marker.setMap?.(visible ? map : null);
    });
  }, [companyCategoryVisible, showMapLayer, showCompanyLayer]);

  useEffect(() => {
    setViewerZoom(1);
  }, [selectedId]);

  useEffect(() => {
    if (editingCircleRadiusField !== null) return;
    if (circleMetrics) {
      setCircleRadiusImageInput(circleMetrics.radiusImagePx.toFixed(1));
      setCircleRadiusMetersInput(
        circleMetrics.radiusMeters !== null && circleMetrics.radiusMeters !== undefined
          ? circleMetrics.radiusMeters.toFixed(2)
          : '',
      );
      return;
    }
    setCircleRadiusImageInput('');
    setCircleRadiusMetersInput('');
  }, [circleMetrics, editingCircleRadiusField]);

  useEffect(() => {
    if (editingMapCircleRadius) return;
    if (mapShape?.type === 'circle') {
      setMapCircleRadiusKmInput((mapShape.radius / 1000).toFixed(3));
      return;
    }
    setMapCircleRadiusKmInput('');
  }, [editingMapCircleRadius, mapShape]);

  useEffect(() => {
    setMessages([]);
    setThinkingSteps([]);
    setLegendCalibrationMessage('');
    setScaleCalibrationMessage('');
    setChatImageAttachment(null);
    clearRelationColors();
  }, [selectedId]);

  useEffect(() => {
    window.localStorage.setItem(STORAGE_KEYS.libraryWidth, String(libraryWidth));
  }, [libraryWidth]);

  useEffect(() => {
    if (!error) return;
    const timer = window.setTimeout(() => setError(''), 3000);
    return () => window.clearTimeout(timer);
  }, [error]);

  useEffect(() => {
    window.localStorage.setItem(STORAGE_KEYS.chatWidth, String(chatWidth));
  }, [chatWidth]);

  useEffect(() => {
    window.localStorage.setItem(STORAGE_KEYS.companyDrawerWidth, String(companyDrawerWidth));
  }, [companyDrawerWidth]);

  useEffect(() => {
    window.localStorage.setItem(STORAGE_KEYS.belowInfoHeight, String(belowInfoHeight));
  }, [belowInfoHeight]);

  useEffect(() => {
    window.localStorage.setItem(STORAGE_KEYS.taskHint, chatMode);
  }, [chatMode]);

  useEffect(() => {
    if (!showMapLayer || !isMapShapeTarget || !amapSdkReady || !window.AMap?.plugin || !amapInstanceRef.current) {
      closeMapMouseTool();
      return;
    }

    const startDrawing = () => {
      if (!window.AMap?.MouseTool || !amapInstanceRef.current) return;
      const mouseTool = mapMouseToolRef.current ?? new window.AMap.MouseTool(amapInstanceRef.current);
      mapMouseToolRef.current = mouseTool;
      closeMapMouseTool();
      if (mode === 'circle' && isMapShapeTarget && !mapCircleDrawingEnabled) {
        if (mapShape) renderMapShapeOverlay(mapShape);
        return;
      }
      if (mapShape) {
        renderMapShapeOverlay(mapShape);
        return;
      }
      if (mode === 'polygon') {
        mouseTool.polygon?.(MAP_SHAPE_STYLE);
        return;
      }
      if (mode === 'rectangle') {
        mouseTool.rectangle?.(MAP_SHAPE_STYLE);
        return;
      }
      mouseTool.circle?.(MAP_SHAPE_STYLE);
    };

    const handleDraw = (event: { type?: string; obj?: unknown }) => {
      clearMapShapeOverlay();
      if (!event.obj) {
        closeMapMouseTool();
        setMapShape(null);
        return;
      }
      const circleOverlay = event.obj as AMapCircle;
      const center = circleOverlay.getCenter?.();
      const radius = circleOverlay.getRadius?.() ?? 0;
      if (center && radius > 0) {
        setMapShape({
          type: 'circle',
          center: { x: center.lng, y: center.lat },
          radius,
        });
        mapDrawOverlayRef.current = circleOverlay;
        closeMapMouseTool();
        return;
      }

      const rectangleOverlay = event.obj as AMapRectangle;
      const bounds = rectangleOverlay.getBounds?.();
      if (mode === 'rectangle' && bounds) {
        const southWest = bounds.getSouthWest();
        const northEast = bounds.getNorthEast();
        const rectangleShape = [
          { x: southWest.lng, y: southWest.lat },
          { x: northEast.lng, y: southWest.lat },
          { x: northEast.lng, y: northEast.lat },
          { x: southWest.lng, y: northEast.lat },
        ];
        setMapShape({ type: 'polygon', points: rectangleShape });
        mapDrawOverlayRef.current = rectangleOverlay as AMapPolygon;
        closeMapMouseTool();
        return;
      }

      const polygonOverlay = event.obj as AMapPolygon;
      const path = normalizeMapPath(polygonOverlay.getPath?.());
      if (path.length >= 3) {
        setMapShape({ type: 'polygon', points: path });
        mapDrawOverlayRef.current = polygonOverlay;
        closeMapMouseTool();
        return;
      }
      closeMapMouseTool();
      setMapShape(null);
    };

    let disposed = false;
    window.AMap.plugin(['AMap.MouseTool'], () => {
      if (disposed || !window.AMap?.MouseTool || !amapInstanceRef.current) return;
      const mouseTool = mapMouseToolRef.current ?? new window.AMap.MouseTool(amapInstanceRef.current);
      mapMouseToolRef.current = mouseTool;
      mouseTool.off?.('draw', handleDraw);
      mouseTool.on?.('draw', handleDraw);
      startDrawing();
    });

    return () => {
      disposed = true;
      mapMouseToolRef.current?.off?.('draw', handleDraw);
      closeMapMouseTool();
    };
  }, [showMapLayer, isMapShapeTarget, amapSdkReady, mode, mapShape, mapCircleDrawingEnabled]);

  useEffect(() => {
    window.localStorage.setItem(STORAGE_KEYS.conversationMap, JSON.stringify(conversationMap));
  }, [conversationMap]);

  useEffect(() => {
    if (!showMapLayer) {
      if (companyRenderTimerRef.current !== null) {
        window.clearTimeout(companyRenderTimerRef.current);
        companyRenderTimerRef.current = null;
      }
      if (poiRenderTimerRef.current !== null) {
        window.clearTimeout(poiRenderTimerRef.current);
        poiRenderTimerRef.current = null;
      }
      const map = amapInstanceRef.current;
      const center = map?.getCenter?.();
      const zoom = map?.getZoom?.();
      if (center && typeof zoom === 'number') {
        mapViewRef.current = { center: [center.lng, center.lat], zoom };
      }
      amapInstanceRef.current?.destroy?.();
      amapInstanceRef.current = null;
      mapMouseToolRef.current = null;
      mapDrawOverlayRef.current = null;
      clearMapGuideOverlays();
      mapReadyRef.current = false;
      companyInfoWindowRef.current = null;
      poiInfoWindowRef.current = null;
      landUseInfoWindowRef.current = null;
      clearCompanyMarkers();
      clearPoiMarkers();
      clearLandUsePolygons();
      setVisibleCompanies([]);
      setVisiblePois([]);
      setSelectedCompanyId(null);
      setSelectedCompanyDetail(null);
      setCompanyLayerStatus({ state: 'idle', message: '高德地图图层已关闭' });
      return;
    }
    if (!amapSdkReady) return;
    let cancelled = false;
    let frame = 0;

    const createMap = () => {
      if (cancelled || !amapContainerRef.current || !window.AMap) return;
      const rect = amapContainerRef.current.getBoundingClientRect();
      if (rect.width < 24 || rect.height < 24) {
        frame = window.requestAnimationFrame(createMap);
        return;
      }
      const initialView = mapViewRef.current;
      amapInstanceRef.current?.destroy?.();
      amapInstanceRef.current = new window.AMap.Map(amapContainerRef.current, {
        viewMode: '2D',
        zoom: initialView.zoom,
        center: initialView.center,
        resizeEnable: true,
        mapStyle: 'amap://styles/whitesmoke',
      });
      if (mapLayerMode === 'satellite') {
        amapInstanceRef.current.setLayers?.([
          new window.AMap.TileLayer.Satellite(),
          new window.AMap.TileLayer.RoadNet(),
        ]);
      }
      if (pendingMapJumpRef.current) {
        amapInstanceRef.current.setCenter?.(pendingMapJumpRef.current.center);
        amapInstanceRef.current.setZoom?.(pendingMapJumpRef.current.zoom);
        pendingMapJumpRef.current = null;
      }
      mapReadyRef.current = true;
      companyInfoWindowRef.current = new window.AMap.InfoWindow({ offset: [0, -24] });
      window.setTimeout(() => amapInstanceRef.current?.resize?.(), 0);
    };

    createMap();
    return () => {
      cancelled = true;
      clearMapGuideOverlays();
      if (frame) window.cancelAnimationFrame(frame);
    };
  }, [showMapLayer, mapLayerMode, amapSdkReady]);

  useEffect(() => {
    if (!showMapLayer || !amapInstanceRef.current || !mapReadyRef.current) return;
    const timer = window.setTimeout(() => {
      amapInstanceRef.current?.resize?.();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [
    showMapLayer,
    showDiagramLayer,
    selectedId,
    libraryCollapsed,
    showCompanyPanel,
    showCompanyLayer,
    libraryWidth,
    chatWidth,
    companyDrawerWidth,
    belowInfoHeight,
  ]);

  useEffect(() => {
    if (!showMapLayer || !showCompanyLayer || !window.AMap || !amapInstanceRef.current) {
      clearCompanyMarkers();
      setVisibleCompanies([]);
      setSelectedCompanyId(null);
      setSelectedCompanyDetail(null);
      if (showMapLayer) {
        setCompanyLayerStatus({ state: 'idle', message: '企业数据图层已关闭' });
      }
      return;
    }
    const map = amapInstanceRef.current;
    const amap = window.AMap;

    const renderCompanies = async () => {
      const zoom = map.getZoom?.() ?? COMPANY_MIN_ZOOM;
      const center = map.getCenter?.();
      if (center) {
        mapViewRef.current = { center: [center.lng, center.lat], zoom };
      }
      if (zoom < COMPANY_MIN_ZOOM) {
        clearCompanyMarkers();
        setCompanyLayerStatus({
          state: 'idle',
          message: `缩放到 ${COMPANY_MIN_ZOOM} 级及以上后显示企业点`,
        });
        return;
      }
      const bounds = map.getBounds?.();
      if (!bounds) return;
      const southWest = bounds.getSouthWest();
      const northEast = bounds.getNorthEast();
      const requestId = ++companyRequestIdRef.current;
      setCompanyLayerStatus({ state: 'loading', message: '正在加载企业点位...' });
      try {
        const result = await listCompaniesInBounds({
          minLng: southWest.lng,
          minLat: southWest.lat,
          maxLng: northEast.lng,
          maxLat: northEast.lat,
          limit: COMPANY_MARKER_LIMIT,
          keyword: companyKeyword,
          district: companyDistrict === '全部' ? '' : companyDistrict,
        });
        if (requestId !== companyRequestIdRef.current) return;
        const filteredCompanies = mapShape
          ? result.items.filter((item) => isPointInsideMapShape({ x: item.lng, y: item.lat }, mapShape))
          : result.items;
        clearCompanyMarkers();
        setVisibleCompanies(filteredCompanies);
        setSelectedCompanyId((current) => (current !== null && filteredCompanies.some((item) => item.id === current) ? current : null));
        setSelectedCompanyDetail((current) => (current !== null && filteredCompanies.some((item) => item.id === current.id) ? current : null));
        // Spiral-offset for duplicate coordinates so markers don't fully overlap
        const coordCounts = new Map<string, number>();
        for (const company of filteredCompanies) {
          const key = `${company.lng},${company.lat}`;
          const idx = coordCounts.get(key) ?? 0;
          coordCounts.set(key, idx + 1);
          let markerLng = company.lng;
          let markerLat = company.lat;
          if (idx > 0) {
            const angle = idx * 2.39996; // golden angle in radians
            const r = 0.00008 * Math.sqrt(idx);
            markerLng += r * Math.cos(angle);
            markerLat += r * Math.sin(angle) * 0.85;
          }
          const relation = companyRelationMapRef.current.get(company.id) ?? 'other';
          const markerColor = relation ? (RELATION_COLORS[relation] || RELATION_COLORS.other) : DEFAULT_MARKER_COLOR;
          const visible = companyCategoryVisible.has(relation);
          const marker = new amap.Marker({
            position: [markerLng, markerLat],
            title: company.company_name,
            extData: company,
            content: `<div class="relation-marker-dot" style="background:${markerColor};"></div>`,
            map: visible ? map : null,
          });
          companyMarkerMapRef.current.set(company.id, marker);
          marker.on?.('click', () => {
            const point = marker.getExtData?.() as CompanyPoint | undefined;
            if (!point) return;
            setSelectedCompanyId(point.id);
            void (async () => {
              const cached = companyDetailCacheRef.current.get(point.id);
              const detail: CompanyDetail = cached ?? await getCompanyDetail(point.id);
              if (!cached) companyDetailCacheRef.current.set(point.id, detail);
              setSelectedCompanyDetail(detail);
              if (!companyInfoWindowRef.current) return;
              const status = escapeHtml(detail.status);
              const legalRepresentative = escapeHtml(detail.legal_representative);
              const registeredCapital = escapeHtml(detail.registered_capital);
              const industry = escapeHtml(detail.industry);
              const district = escapeHtml(detail.district);
              const address = escapeHtml(detail.address);
              const insuredCount = escapeHtml(detail.insured_count);
              const content = [
                `<div style="min-width:300px;max-width:380px;padding:2px 2px 0;line-height:1.5;color:#0f172a;font-family:'Microsoft YaHei',system-ui,sans-serif;">`,
                `<div style="margin-bottom:10px;padding-bottom:10px;border-bottom:1px solid #e2e8f0;">`,
                `<div style="font-size:16px;font-weight:700;color:#0f172a;line-height:1.4;word-break:break-word;">${escapeHtml(detail.company_name)}</div>`,
                `<div style="margin-top:6px;display:inline-flex;align-items:center;padding:3px 10px;border-radius:999px;background:#eff6ff;color:#1d4ed8;font-size:12px;font-weight:600;">${status}</div>`,
                `</div>`,
                `<div style="display:grid;grid-template-columns:84px 1fr;gap:8px 10px;font-size:13px;">`,
                `<div style="color:#64748b;font-weight:600;">法人</div><div style="color:#0f172a;">${legalRepresentative}</div>`,
                `<div style="color:#64748b;font-weight:600;">注册资本</div><div style="color:#0f172a;">${registeredCapital}</div>`,
                `<div style="color:#64748b;font-weight:600;">所属行业</div><div style="color:#0f172a;">${industry}</div>`,
                `<div style="color:#64748b;font-weight:600;">所属区县</div><div style="color:#0f172a;">${district}</div>`,
                `<div style="color:#64748b;font-weight:600;">参保人数</div><div style="color:#0f172a;">${insuredCount}</div>`,
                `</div>`,
                `<div style="margin-top:12px;padding:10px 12px;border-radius:12px;background:#f8fafc;border:1px solid #e2e8f0;">`,
                `<div style="margin-bottom:4px;color:#64748b;font-size:12px;font-weight:700;">注册地址</div>`,
                `<div style="color:#0f172a;font-size:13px;line-height:1.65;word-break:break-word;">${address}</div>`,
                `</div>`,
                `</div>`,
              ].join('');
              companyInfoWindowRef.current = new amap.InfoWindow({ offset: [0, -24], content });
              companyInfoWindowRef.current.open?.(map, [detail.lng, detail.lat]);
            })().catch((err) => {
              console.error('load company detail failed', err);
              setError('企业详情加载失败');
            });
          });
        }
        setCompanyLayerStatus({
          state: 'ready',
          message: mapShape
            ? `当前圈选范围显示 ${filteredCompanies.length} 个企业点`
            : result.truncated
              ? `当前视野已显示前 ${result.total} 个企业点，请继续放大地图或收窄筛选`
              : `当前视野显示 ${filteredCompanies.length} 个企业点`,
        });
      } catch (err) {
        if (requestId !== companyRequestIdRef.current) return;
        console.error('load companies failed', err);
        clearCompanyMarkers();
        setVisibleCompanies([]);
        setSelectedCompanyId(null);
        setSelectedCompanyDetail(null);
        setCompanyLayerStatus({ state: 'error', message: '企业点位加载失败' });
      }
    };

    const scheduleRenderCompanies = () => {
      if (companyRenderTimerRef.current !== null) {
        window.clearTimeout(companyRenderTimerRef.current);
      }
      companyRenderTimerRef.current = window.setTimeout(() => {
        void renderCompanies();
      }, 180);
    };

    scheduleRenderCompanies();
    map.on?.('moveend', scheduleRenderCompanies);
    map.on?.('zoomend', scheduleRenderCompanies);
    return () => {
      if (companyRenderTimerRef.current !== null) {
        window.clearTimeout(companyRenderTimerRef.current);
        companyRenderTimerRef.current = null;
      }
      map.off?.('moveend', scheduleRenderCompanies);
      map.off?.('zoomend', scheduleRenderCompanies);
    };
  }, [showMapLayer, showCompanyLayer, companyKeyword, companyDistrict, showDiagramLayer, mapShape]);

  useEffect(() => {
    if (!showPoiLayer) return;
    if (poiCategories.length > 0) return;
    let cancelled = false;
    void (async () => {
      try {
        const items = await listPoiCategories();
        if (cancelled) return;
        setPoiCategories(items);
        setEnabledPoiCategories((current) => (current.length > 0 ? current : items.map((item) => item.name)));
      } catch (err) {
        if (!cancelled) {
          console.error('load poi categories failed', err);
          setError(String((err as Error).message || err));
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [showPoiLayer, poiCategories.length]);

  useEffect(() => {
    if (!showMapLayer || !showPoiLayer || !window.AMap || !amapInstanceRef.current) {
      clearPoiMarkers();
      setVisiblePois([]);
      return;
    }
    if (enabledPoiCategories.length === 0) {
      clearPoiMarkers();
      setVisiblePois([]);
      return;
    }
    const map = amapInstanceRef.current;
    const amap = window.AMap;

    const renderPois = async () => {
      const zoom = map.getZoom?.() ?? POI_MIN_ZOOM;
      if (zoom < POI_MIN_ZOOM) {
        clearPoiMarkers();
        setVisiblePois([]);
        return;
      }
      const bounds = map.getBounds?.();
      if (!bounds) return;
      const southWest = bounds.getSouthWest();
      const northEast = bounds.getNorthEast();
      const requestId = ++poiRequestIdRef.current;
      try {
        const result = await listPoisInBounds({
          minLng: southWest.lng,
          minLat: southWest.lat,
          maxLng: northEast.lng,
          maxLat: northEast.lat,
          limit: POI_MARKER_LIMIT,
          categories: enabledPoiCategories,
        });
        if (requestId !== poiRequestIdRef.current) return;
        const filteredPois = mapShape
          ? result.items.filter((item) => isPointInsideMapShape({ x: item.lng, y: item.lat }, mapShape))
          : result.items;
        clearPoiMarkers();
        setVisiblePois(filteredPois);
        poiInfoWindowRef.current = new amap.InfoWindow({ offset: [0, -16] });
        for (const poi of filteredPois) {
          const color = poiCategoryColorMap[poi.major_category ?? '未分类'] ?? POI_CATEGORY_COLORS[0];
          const marker = new amap.Marker({
            position: [poi.lng, poi.lat],
            title: poi.name,
            extData: poi,
            content: `<div class="poi-marker-dot" style="background:${color};"></div>`,
            map,
          });
          marker.on?.('mouseover', () => {
            const point = marker.getExtData?.() as PoiPoint | undefined;
            if (!point) return;
            const content = [
              `<div style="min-width:220px;max-width:300px;padding:2px 2px 0;line-height:1.5;color:#0f172a;font-family:'Microsoft YaHei',system-ui,sans-serif;">`,
              `<div style="font-size:15px;font-weight:700;margin-bottom:10px;line-height:1.4;word-break:break-word;">${escapeHtml(point.name)}</div>`,
              `<div style="display:grid;grid-template-columns:64px 1fr;gap:6px 8px;font-size:13px;">`,
              `<div style="color:#64748b;font-weight:600;">大类</div><div>${escapeHtml(point.major_category ?? '未分类')}</div>`,
              `<div style="color:#64748b;font-weight:600;">中类</div><div>${escapeHtml(point.middle_category ?? '未分类')}</div>`,
              `<div style="color:#64748b;font-weight:600;">小类</div><div>${escapeHtml(point.minor_category ?? '未分类')}</div>`,
              `</div>`,
              `</div>`,
            ].join('');
            poiInfoWindowRef.current = new amap.InfoWindow({ offset: [0, -16], content });
            poiInfoWindowRef.current.open?.(map, [point.lng, point.lat]);
          });
          marker.on?.('mouseout', () => {
            poiInfoWindowRef.current?.close?.();
          });
          poiMarkerMapRef.current.set(poi.id, marker);
        }
      } catch (err) {
        if (requestId !== poiRequestIdRef.current) return;
        console.error('load pois failed', err);
        clearPoiMarkers();
        setVisiblePois([]);
      }
    };

    const scheduleRenderPois = () => {
      if (poiRenderTimerRef.current !== null) {
        window.clearTimeout(poiRenderTimerRef.current);
      }
      poiRenderTimerRef.current = window.setTimeout(() => {
        void renderPois();
      }, 180);
    };

    scheduleRenderPois();
    map.on?.('moveend', scheduleRenderPois);
    map.on?.('zoomend', scheduleRenderPois);
    return () => {
      if (poiRenderTimerRef.current !== null) {
        window.clearTimeout(poiRenderTimerRef.current);
        poiRenderTimerRef.current = null;
      }
      map.off?.('moveend', scheduleRenderPois);
      map.off?.('zoomend', scheduleRenderPois);
    };
  }, [showMapLayer, showPoiLayer, enabledPoiCategories, showDiagramLayer, mapShape]);

  useEffect(() => {
    if (!showMapLayer || !showLandUseLayer || !window.AMap || !amapInstanceRef.current) {
      clearLandUsePolygons();
      return;
    }

    const map = amapInstanceRef.current;
    const amap = window.AMap;
    let cancelled = false;

    const renderLandUse = async () => {
      const dataset = landUseDatasetRef.current ?? await getLandUseDataset();
      landUseDatasetRef.current = dataset;
      if (cancelled) return;

      clearLandUsePolygons();
      landUseInfoWindowRef.current = new amap.InfoWindow({ offset: [0, -8] });

      const filteredFeatures = mapShape
        ? dataset.geojson.features.filter((feature) => isPointInsideMapShape(getLandUseFeatureCenter(feature), mapShape))
        : dataset.geojson.features;

      for (const feature of filteredFeatures) {
        const featureId = Number(feature.properties.feature_id);
        const polygon = new amap.Polygon({
          path: buildLandUsePolygonPath(feature),
          bubble: true,
          extData: { feature },
          map,
          ...getLandUsePolygonStyle(feature, 'base'),
        });

        polygon.on?.('mouseover', () => {
          if (selectedLandUseFeatureRef.current === featureId) return;
          hoveredLandUseFeatureRef.current = featureId;
          polygon.setOptions?.(getLandUsePolygonStyle(feature, 'hover'));
        });
        polygon.on?.('mouseout', () => {
          hoveredLandUseFeatureRef.current = hoveredLandUseFeatureRef.current === featureId ? null : hoveredLandUseFeatureRef.current;
          polygon.setOptions?.(
            selectedLandUseFeatureRef.current === featureId
              ? getLandUsePolygonStyle(feature, 'active')
              : getLandUsePolygonStyle(feature, 'base'),
          );
        });
        polygon.on?.('click', (event) => {
          const previousSelectedId = selectedLandUseFeatureRef.current;
          if (previousSelectedId !== null && previousSelectedId !== featureId) {
            const previousFeature = landUsePolygonMapRef.current.get(previousSelectedId)?.getExtData?.() as { feature?: LandUsePolygonFeature } | undefined;
            if (previousFeature?.feature) {
              landUsePolygonMapRef.current.get(previousSelectedId)?.setOptions?.(getLandUsePolygonStyle(previousFeature.feature, 'base'));
            }
          }
          selectedLandUseFeatureRef.current = featureId;
          polygon.setOptions?.(getLandUsePolygonStyle(feature, 'active'));

          const rawProperties = feature.properties ?? {};
          const areaSquareMeters = calculateLandUseFeatureAreaSquareMeters(feature);
          const extraEntries = Object.entries(rawProperties).filter(([key]) => !['feature_id', 'interactive_label'].includes(key));
          const content = [
            `<div style="min-width:220px;max-width:320px;padding:2px 2px 0;line-height:1.5;color:#0f172a;font-family:'Microsoft YaHei',system-ui,sans-serif;">`,
            `<div style="font-size:15px;font-weight:700;margin-bottom:8px;">${escapeHtml(feature.properties.interactive_label ?? `地块 ${featureId}`)}</div>`,
            `<div style="display:grid;grid-template-columns:88px 1fr;gap:6px 8px;font-size:13px;">`,
            `<div style="color:#64748b;font-weight:600;">编号</div><div>${escapeHtml(featureId)}</div>`,
            `<div style="color:#64748b;font-weight:600;">类型</div><div>${escapeHtml(getLandUseGeometryLabel(feature))}</div>`,
            `<div style="color:#64748b;font-weight:600;">顶点数</div><div>${escapeHtml(countLandUseVertices(feature))}</div>`,
            `<div style="color:#64748b;font-weight:600;">用地面积</div><div>${escapeHtml(formatMetricValue(areaSquareMeters, 2))} ㎡</div>`,
            `</div>`,
            extraEntries.length > 0
              ? `<div style="margin-top:10px;padding-top:10px;border-top:1px solid #e2e8f0;font-size:12px;color:#334155;">${extraEntries.map(([key, value]) => `<div><b>${escapeHtml(key)}</b>：${escapeHtml(value)}</div>`).join('')}</div>`
              : `<div style="margin-top:10px;padding-top:10px;border-top:1px solid #e2e8f0;font-size:12px;color:#64748b;">源文件没有属性字段，当前提供的是可交互地块样式。</div>`,
            `</div>`,
          ].join('');
          landUseInfoWindowRef.current = new amap.InfoWindow({ offset: [0, -8], content });
          landUseInfoWindowRef.current.open?.(
            map,
            event.lnglat
              ? [event.lnglat.lng, event.lnglat.lat]
              : getLandUseAnchor(feature),
          );
        });

        landUsePolygonMapRef.current.set(featureId, polygon);
      }
      if (!cancelled && mapShape) {
        window.setTimeout(() => {
          if (!cancelled) renderMapShapeOverlay(mapShape);
        }, 0);
      }
    };

    void renderLandUse().catch((err) => {
      if (!cancelled) {
        console.error('load land use layer failed', err);
        setError(String((err as Error).message || err));
      }
    });

    return () => {
      cancelled = true;
      clearLandUsePolygons();
    };
  }, [showMapLayer, showLandUseLayer, mapShape]);

  useEffect(() => {
    return () => {
      amapInstanceRef.current?.destroy?.();
      amapInstanceRef.current = null;
      mapMouseToolRef.current = null;
      mapDrawOverlayRef.current = null;
    };
  }, []);

  async function refreshDiagrams() {
    const items = await listDiagrams();
    setDiagrams(items);
    if (selectedId === null && items[0]) {
      setSelectedId(items[0].id);
      return;
    }
    if (selectedId !== null && !items.some((item) => item.id === selectedId) && items[0]) {
      setSelectedId(items[0].id);
    }
  }

  async function handleScaleCalibration(payload: {
    metersPerPixel?: number;
    referenceDistanceMeters?: number;
    referencePixelLength?: number;
    scaleText?: string;
  }) {
    if (selectedDiagram === null) return;
    setScaleCalibrating(true);
    setError('');
    setScaleCalibrationMessage('');
    try {
      const updated = await calibrateDiagramScale(selectedDiagram.id, payload);
      setDiagrams((current) => current.map((diagram) => (diagram.id === updated.id ? updated : diagram)));
      await refreshDiagrams();
      setScaleCalibrationMessage(`比例尺已更新：1 px = ${formatNumber(updated.scale_json.meters_per_pixel)} m`);
    } catch (err) {
      setError(String((err as Error).message || err));
    } finally {
      setScaleCalibrating(false);
    }
  }

  async function handleLegendRecalibration() {
    if (selectedDiagram === null) return;
    setLegendCalibrating(true);
    setLegendCalibrationMessage('');
    setError('');
    try {
      const updated = await recalibrateDiagramLegend(selectedDiagram.id);
      setDiagrams((current) => current.map((diagram) => (diagram.id === updated.id ? updated : diagram)));
      await refreshDiagrams();
      setLegendCalibrationMessage(`图例已重新校准，共更新 ${Object.keys(updated.legend_json ?? {}).length} 项。请重新计算圈选区域。`);
    } catch (err) {
      setError(String((err as Error).message || err));
    } finally {
      setLegendCalibrating(false);
    }
  }

  async function handleRenameDiagram(diagram: Diagram) {
    const nextName = window.prompt('请输入新的图纸名称', diagram.filename);
    if (nextName === null) return;
    const trimmed = nextName.trim();
    if (!trimmed || trimmed === diagram.filename) return;
    setError('');
    try {
      const updated = await renameDiagram(diagram.id, trimmed);
      setDiagrams((current) => current.map((item) => (item.id === updated.id ? updated : item)));
    } catch (err) {
      setError(String((err as Error).message || err));
    }
  }

  async function handleDeleteDiagram(diagram: Diagram) {
    const confirmed = window.confirm(`确认删除图纸“${diagram.filename}”吗？此操作不可恢复。`);
    if (!confirmed) return;
    setError('');
    try {
      await deleteDiagram(diagram.id);
      setDiagrams((current) => {
        const nextItems = current.filter((item) => item.id !== diagram.id);
        if (selectedId === diagram.id) {
          setSelectedId(nextItems[0]?.id ?? null);
        }
        return nextItems;
      });
      if (selectedId === diagram.id) {
        resetShape();
      }
    } catch (err) {
      setError(String((err as Error).message || err));
    }
  }

  async function handleUpload(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (file === undefined) return;
    setLoading(true);
    setThinkingSteps([]);
    setError('');
    try {
      const diagram = await uploadDiagram(file);
      await refreshDiagrams();
      setSelectedId(diagram.id);
      setMessages((current) => [...current, { id: crypto.randomUUID(), role: 'assistant', content: `已上传并处理图纸：${diagram.filename}` }]);
    } catch (err) {
      setError(String((err as Error).message || err));
    } finally {
      setLoading(false);
    }
  }

  function closeMapMouseTool() {
    mapMouseToolRef.current?.close?.(false);
  }

  function clearMapShapeOverlay() {
    mapDrawOverlayRef.current?.setMap?.(null);
    mapDrawOverlayRef.current = null;
  }

  function clearMapGuideOverlays() {
    mapGuideOverlayRefs.current.forEach((overlay) => overlay.setMap?.(null));
    mapGuideOverlayRefs.current = [];
  }

  function renderMapCircleGuideOverlays(shape: Extract<RegionShape, { type: 'circle' }>) {
    if (!window.AMap || !amapInstanceRef.current || !showLandUseLayer) return;
    clearMapGuideOverlays();

    const map = amapInstanceRef.current;
    const offset = getCircleRadiusLngLatOffset(shape.center, shape.radius);
    const centerPosition: [number, number] = [shape.center.x, shape.center.y];
    const edgePosition: [number, number] = [shape.center.x + offset.lng, shape.center.y];
    const midPosition: [number, number] = [shape.center.x + offset.lng / 2, shape.center.y];
    const radiusKmText = `${(shape.radius / 1000).toFixed(3)} km`;

    const guideLine = new window.AMap.Polyline({
      path: [centerPosition, edgePosition],
      strokeColor: '#38bdf8',
      strokeWeight: 3,
      strokeOpacity: 0.95,
      strokeStyle: 'dashed',
      lineJoin: 'round',
      map,
    });

    const centerMarker = new window.AMap.Marker({
      position: centerPosition,
      offset: [-7, -7],
      content: '<div class="map-circle-guide-center-marker"></div>',
      map,
    });

    const edgeMarker = new window.AMap.Marker({
      position: edgePosition,
      offset: [-6, -6],
      content: '<div class="map-circle-guide-edge-marker"></div>',
      map,
    });

    const centerText = new window.AMap.Text({
      text: '圆心',
      position: centerPosition,
      offset: [12, -16],
      style: {
        padding: '2px 6px',
        borderRadius: '999px',
        border: '1px solid rgba(8, 47, 73, 0.6)',
        background: 'rgba(15, 23, 42, 0.92)',
        color: '#e0f2fe',
        fontSize: '12px',
        fontWeight: '700',
        lineHeight: '1.2',
        boxShadow: '0 8px 20px rgba(0, 0, 0, 0.22)',
      },
      map,
    });

    const radiusText = new window.AMap.Text({
      text: `半径 ${radiusKmText}`,
      position: midPosition,
      offset: [0, -22],
      style: {
        padding: '3px 8px',
        borderRadius: '999px',
        border: '1px solid rgba(14, 165, 233, 0.45)',
        background: 'rgba(15, 23, 42, 0.92)',
        color: '#e0f2fe',
        fontSize: '12px',
        fontWeight: '700',
        lineHeight: '1.2',
        whiteSpace: 'nowrap',
        boxShadow: '0 8px 20px rgba(0, 0, 0, 0.22)',
      },
      map,
    });

    mapGuideOverlayRefs.current = [guideLine, centerMarker, edgeMarker, centerText, radiusText];
  }

  function renderMapShapeOverlay(shape: RegionShape | null = mapShape) {
    if (!window.AMap || !amapInstanceRef.current || !shape) return;
    clearMapShapeOverlay();
    clearMapGuideOverlays();
    if (shape.type === 'circle') {
      mapDrawOverlayRef.current = new window.AMap.Polygon({
        path: buildCirclePolygonPath(shape.center, shape.radius),
        map: amapInstanceRef.current,
        ...MAP_SHAPE_STYLE,
      });
      if (isLandUseMapCircleEditorEnabled) {
        renderMapCircleGuideOverlays(shape);
      }
      return;
    }
    if (shape.points.length < 3) return;
    mapDrawOverlayRef.current = new window.AMap.Polygon({
      path: [shape.points.map((point) => [point.x, point.y] as [number, number])],
      map: amapInstanceRef.current,
      ...MAP_SHAPE_STYLE,
    });
  }

  function resetShape() {
    closeMapMouseTool();
    clearMapShapeOverlay();
    clearMapGuideOverlays();
    setPoints([]);
    setCircle(null);
    setRectangle(null);
    setMapShape(null);
    setCircleHandleAngle(0);
    setDraggingCircle(false);
    setDraggingRectangle(false);
    setCircleDragMode(null);
    setMapCircleRadiusKmInput('');
    setEditingMapCircleRadius(false);
    setDragOffset(null);
  }

  function toCanvasPoint(event: ReactMouseEvent<SVGSVGElement>) {
    return toSvgPoint(event.currentTarget, event.clientX, event.clientY);
  }

  function toOverlayPoint(clientX: number, clientY: number) {
    const svg = overlayRef.current;
    if (!svg) return { x: clientX, y: clientY };
    return toSvgPoint(svg, clientX, clientY);
  }

  function toSvgPoint(svg: SVGSVGElement, clientX: number, clientY: number) {
    const rect = svg.getBoundingClientRect();
    const fallbackPoint = {
      x: clamp(clientX - rect.left, 0, rect.width || displaySize.width),
      y: clamp(clientY - rect.top, 0, rect.height || displaySize.height),
    };
    try {
      const point = svg.createSVGPoint();
      point.x = clientX;
      point.y = clientY;
      const matrix = svg.getScreenCTM();
      if (!matrix) return fallbackPoint;
      const transformed = point.matrixTransform(matrix.inverse());
      if (!Number.isFinite(transformed.x) || !Number.isFinite(transformed.y)) return fallbackPoint;
      return {
        x: clamp(transformed.x, 0, displaySize.width),
        y: clamp(transformed.y, 0, displaySize.height),
      };
    } catch (error) {
      console.warn('svg point transform failed, fallback to rect mapping', error);
      return fallbackPoint;
    }
  }

  function displayPointToImagePoint(point: Point) {
    if (selectedDiagram === null || displaySize.width <= 0 || displaySize.height <= 0) return point;
    return scalePoint(point, displaySize, selectedDiagram);
  }

  function imagePointToDisplay(point: Point) {
    if (selectedDiagram === null) return point;
    return imagePointToDisplayPoint(point, displaySize, selectedDiagram);
  }

  function displayRadiusToImageRadius(radius: number) {
    if (selectedDiagram === null || displaySize.width <= 0) return radius;
    return (radius / displaySize.width) * selectedDiagram.image_width;
  }

  function imageRadiusToDisplay(radius: number) {
    if (selectedDiagram === null) return radius;
    return imageRadiusToDisplayRadius(radius, displaySize.width, selectedDiagram);
  }

  function handleOverlayClick(event: ReactMouseEvent<SVGSVGElement>) {
    if (mode !== 'polygon') return;
    const point = toCanvasPoint(event);
    if (!Number.isFinite(point.x) || !Number.isFinite(point.y)) return;
    setPoints((current) => [...current, displayPointToImagePoint(point)]);
  }

  function handleOverlayContextMenu(event: ReactMouseEvent<SVGSVGElement>) {
    if (mode !== 'polygon') return;
    event.preventDefault();
    setPoints((current) => current.slice(0, -1));
  }

  function handleRectangleDown(event: ReactMouseEvent<SVGSVGElement>) {
    if (event.button !== 0) return;
    if (mode !== 'rectangle') return;
    const point = toCanvasPoint(event);
    const imagePoint = displayPointToImagePoint(point);
    setRectangle({ start: imagePoint, end: imagePoint });
    setDraggingRectangle(true);
  }

  function handleRectangleMove(event: ReactMouseEvent<SVGSVGElement>) {
    if (mode !== 'rectangle' || !draggingRectangle || !rectangle) return;
    const point = toCanvasPoint(event);
    setRectangle((current) => (
      current
        ? { ...current, end: displayPointToImagePoint(point) }
        : current
    ));
  }

  function handleRectangleUp() {
    if (mode !== 'rectangle') return;
    setDraggingRectangle(false);
  }

  function handleCircleDown(event: ReactMouseEvent<SVGSVGElement>) {
    if (event.button !== 0) return;
    if (mode !== 'circle') return;
    const point = toCanvasPoint(event);
    setCircle({ center: displayPointToImagePoint(point), radius: 0 });
    setCircleHandleAngle(0);
    setDraggingCircle(true);
    setCircleDragMode('create');
    setDragOffset(null);
  }

  function handleCircleCenterDown(event: ReactMouseEvent<SVGCircleElement>) {
    if (mode !== 'circle' || circle === null) return;
    event.stopPropagation();
    const point = toOverlayPoint(event.clientX, event.clientY);
    const center = imagePointToDisplay(circle.center);
    setDraggingCircle(true);
    setCircleDragMode('move-center');
    setDragOffset({ x: point.x - center.x, y: point.y - center.y });
  }

  function handleCircleRadiusHandleDown(event: ReactMouseEvent<SVGCircleElement>) {
    if (mode !== 'circle' || circle === null) return;
    event.stopPropagation();
    setDraggingCircle(true);
    setCircleDragMode('resize');
    setDragOffset(null);
  }

  function handleCircleMove(event: ReactMouseEvent<SVGSVGElement>) {
    if (mode !== 'circle' || draggingCircle === false || circle === null) return;
    const point = toCanvasPoint(event);
    if (circleDragMode === 'move-center') {
      const offset = dragOffset ?? { x: 0, y: 0 };
      setCircle({
        center: displayPointToImagePoint({ x: point.x - offset.x, y: point.y - offset.y }),
        radius: circle.radius,
      });
      return;
    }
    const center = imagePointToDisplay(circle.center);
    const deltaX = point.x - center.x;
    const deltaY = point.y - center.y;
    const radius = displayRadiusToImageRadius(Math.sqrt(deltaX ** 2 + deltaY ** 2));
    if (radius > 0) setCircleHandleAngle(Math.atan2(deltaY, deltaX));
    setCircle({ center: circle.center, radius: clampCircleRadius(radius) });
  }

  function handleCircleUp() {
    if (mode === 'circle') {
      setDraggingCircle(false);
      setCircleDragMode(null);
      setDragOffset(null);
    }
  }

  function updateCircleRadiusByMeters(value: string) {
    if (circle === null || selectedDiagram === null || displaySize.width <= 0) return;
    const nextMeters = Number(value);
    if (!Number.isFinite(nextMeters) || nextMeters < 0 || !Number.isFinite(metersPerPixel) || metersPerPixel <= 0) return;
    const imageRadiusPx = nextMeters / metersPerPixel;
    setCircle({ center: circle.center, radius: clampCircleRadius(imageRadiusPx) });
  }

  function updateCircleRadiusByImagePx(value: string) {
    if (circle === null || selectedDiagram === null || displaySize.width <= 0) return;
    const nextRadiusImagePx = Number(value);
    if (!Number.isFinite(nextRadiusImagePx) || nextRadiusImagePx < 0) return;
    setCircle({ center: circle.center, radius: clampCircleRadius(nextRadiusImagePx) });
  }

  function updateMapCircleRadiusByKilometers(value: string) {
    setMapCircleRadiusKmInput(value);
    if (mapShape?.type !== 'circle') return;
    const nextRadiusKm = Number(value);
    if (!Number.isFinite(nextRadiusKm) || nextRadiusKm < 0) return;
    setMapShape({
      type: 'circle',
      center: mapShape.center,
      radius: clampCircleRadius(nextRadiusKm * 1000),
    });
  }

  function handlePolygonToolClick() {
    setMapCircleDrawingEnabled(false);
    setMode('polygon');
    resetShape();
  }

  function handleRectangleToolClick() {
    setMapCircleDrawingEnabled(false);
    setMode('rectangle');
    resetShape();
  }

  function handleCircleToolClick() {
    if (isMapShapeTarget) {
      if (mode === 'circle' && mapCircleDrawingEnabled) {
        setMapCircleDrawingEnabled(false);
        closeMapMouseTool();
        return;
      }
      setMode('circle');
      setMapCircleDrawingEnabled(true);
      resetShape();
      return;
    }
    setMapCircleDrawingEnabled(false);
    setMode('circle');
    resetShape();
  }

  function buildShape(): RegionShape {
    if (selectedDiagram === null) throw new Error('请先选择图纸');
    if (mode === 'polygon') {
      if (points.length < 3) throw new Error('请先绘制至少3个点的多边形');
      return { type: 'polygon', points };
    }
    if (mode === 'rectangle') {
      if (rectanglePoints.length !== 4) throw new Error('请先框选矩形区域');
      return { type: 'polygon', points: rectanglePoints };
    }
    if (circle === null || circle.radius <= 0) throw new Error('请先绘制圆形区域');
    return {
      type: 'circle',
      center: circle.center,
      radius: circle.radius,
    };
  }

  async function buildMapRangeStatisticsAnswer(questionText: string, shape: RegionShape) {
    const normalizedQuestion = questionText.toLowerCase();
    const wantsPoi = /poi|兴趣点|公共服务|设施|网点/i.test(questionText);
    const wantsCompany = /企业|公司|产业|工商|经营主体/i.test(questionText);
    const includePoi = wantsPoi || (!wantsPoi && !wantsCompany);
    const includeCompany = wantsCompany || (!wantsPoi && !wantsCompany);
    const wantsStructuredBreakdown = /大类|中类|小类|类别|分类|构成|统计/.test(questionText);
    const wantsDirectCount = /(有几个|有几家|有多少家|有多少个|有多少|几个|几家|多少家|多少个|多少|总数|总量|数量)/.test(questionText);
    const bounds = getMapShapeBounds(shape);
    const sections: string[] = [];
    const notes: string[] = [];
    let poiSpecificLine = '';
    let companySpecificLine = '';

    if (includePoi) {
      const result = await listPoisInBounds({ ...bounds, limit: 5000 });
      const scopedItems = result.items.filter((item) => isPointInsideMapShape({ x: item.lng, y: item.lat }, shape));
      const majorRows = countBy(scopedItems, (item) => item.major_category);
      const middleRows = countBy(scopedItems, (item) => item.middle_category);
      const minorRows = countBy(scopedItems, (item) => item.minor_category);
      const poiMatch = findBestMapStatsMatch(questionText, [
        ...minorRows.map(([label, count]) => ({ label, count, level: '小类' })),
        ...middleRows.map(([label, count]) => ({ label, count, level: '中类' })),
        ...majorRows.map(([label, count]) => ({ label, count, level: '大类' })),
      ]);
      if (poiMatch && wantsDirectCount && !wantsStructuredBreakdown) {
        poiSpecificLine = `圈选范围 POI ${poiMatch.level}“${poiMatch.label}”数量：${poiMatch.count}`;
      } else {
        sections.push(`圈选范围 POI 总数：${scopedItems.length}`);
        sections.push(buildCountTable('圈选范围 POI 大类统计', '大类', majorRows));
        if (/中类|小类/.test(normalizedQuestion)) {
          sections.push(buildCountTable('圈选范围 POI 中类统计', '中类', middleRows));
          sections.push(buildCountTable('圈选范围 POI 小类统计', '小类', minorRows));
        }
      }
      if (result.truncated) notes.push('POI 查询触发接口上限，本次统计可能是前 5000 条范围候选数据过滤后的结果。');
    }

    if (includeCompany) {
      const result = await listCompaniesInBounds({ ...bounds, limit: 2000 });
      const scopedItems = result.items.filter((item) => isPointInsideMapShape({ x: item.lng, y: item.lat }, shape));
      const industryRows = countBy(scopedItems, (item) => item.industry);
      const statusRows = countBy(scopedItems, (item) => item.survival_status);
      const companyMatch = findBestMapStatsMatch(questionText, [
        ...industryRows.map(([label, count]) => ({ label, count, level: '行业' })),
        ...statusRows.map(([label, count]) => ({ label, count, level: '状态' })),
      ]);
      if (companyMatch && wantsDirectCount && !wantsStructuredBreakdown) {
        companySpecificLine = `圈选范围企业${companyMatch.level}“${companyMatch.label}”数量：${companyMatch.count}`;
      } else {
        sections.push(`圈选范围企业总数：${scopedItems.length}`);
        sections.push(buildCountTable('圈选范围企业行业统计', '行业', industryRows));
        if (/状态|存续|经营状态/.test(normalizedQuestion)) {
          sections.push(buildCountTable('圈选范围企业状态统计', '状态', statusRows));
        }
      }
      if (result.truncated) notes.push('企业查询触发接口上限，本次统计可能是前 2000 条范围候选数据过滤后的结果。');
    }

    if (poiSpecificLine) sections.unshift(poiSpecificLine);
    if (companySpecificLine) sections.unshift(companySpecificLine);

    return [
      '已按地图圈选范围完成统计。',
      '',
      ...sections,
      notes.length > 0 ? `\n注意：${notes.join(' ')}` : '',
    ].filter(Boolean).join('\n\n');
  }

  async function buildDistrictStatisticsAnswer(questionText: string, district: string) {
    const wantsPoi = /poi|兴趣点|公共服务|设施|网点/i.test(questionText);
    const wantsCompany = /企业|公司|产业|工商|经营主体/i.test(questionText);
    const includePoi = wantsPoi || (!wantsPoi && !wantsCompany);
    const includeCompany = wantsCompany || (!wantsPoi && !wantsCompany);
    const wantsStructuredBreakdown = /大类|中类|小类|类别|分类|构成|统计/.test(questionText);
    const sections: string[] = [];

    if (includePoi) {
      const stats = await getPoiDistrictStats(district);
      sections.push(`${district} POI 总数：${stats.total}`);
      if (wantsStructuredBreakdown || !/(有几个|有几家|有多少|几个|几家|多少|总数|总量|数量)/.test(questionText)) {
        sections.push(buildCountTable(`${district} POI 大类统计`, '大类', stats.by_major));
        if (/中类|小类/.test(questionText)) {
          sections.push(buildCountTable(`${district} POI 中类统计`, '中类', stats.by_middle));
          sections.push(buildCountTable(`${district} POI 小类统计`, '小类', stats.by_minor));
        }
      }
    }

    if (includeCompany) {
      const stats = await getCompanyDistrictStats(district);
      sections.push(`${district} 企业总数：${stats.total}`);
      if (wantsStructuredBreakdown || !/(有几个|有几家|有多少|几个|几家|多少|总数|总量|数量)/.test(questionText)) {
        sections.push(buildCountTable(`${district} 企业行业统计`, '行业', stats.by_industry));
        if (/状态|存续|经营状态/.test(questionText)) {
          sections.push(buildCountTable(`${district} 企业状态统计`, '状态', stats.by_status));
        }
      }
    }

    return [
      `已按 ${district} 行政区划完成统计。`,
      '',
      ...sections,
    ].filter(Boolean).join('\n\n');
  }

  function handleZoomIn() {
    setViewerZoom((current) => clampZoom(Number((current + DIAGRAM_ZOOM_STEP).toFixed(2))));
  }

  function handleZoomOut() {
    setViewerZoom((current) => clampZoom(Number((current - DIAGRAM_ZOOM_STEP).toFixed(2))));
  }

  function handleZoomReset() {
    setViewerZoom(1);
  }

  function handleDiagramWheel(event: ReactWheelEvent<HTMLDivElement>) {
    event.preventDefault();
    setViewerZoom((current) => {
      const next = current + (event.deltaY < 0 ? DIAGRAM_ZOOM_STEP : -DIAGRAM_ZOOM_STEP);
      return clampZoom(Number(next.toFixed(2)));
    });
  }

  function handleDiagramViewportMouseDown(event: ReactMouseEvent<HTMLDivElement>) {
    if (event.button !== 1) return;
    event.preventDefault();
    const viewport = diagramViewportRef.current;
    if (!viewport) return;
    diagramPanRef.current = {
      startX: event.clientX,
      startY: event.clientY,
      scrollLeft: viewport.scrollLeft,
      scrollTop: viewport.scrollTop,
    };
    setPanningDiagram(true);

    const handleMove = (moveEvent: MouseEvent) => {
      const currentViewport = diagramViewportRef.current;
      const panState = diagramPanRef.current;
      if (!currentViewport || !panState) return;
      currentViewport.scrollLeft = panState.scrollLeft - (moveEvent.clientX - panState.startX);
      currentViewport.scrollTop = panState.scrollTop - (moveEvent.clientY - panState.startY);
    };

    const handleUp = () => {
      diagramPanRef.current = null;
      setPanningDiagram(false);
      window.removeEventListener('mousemove', handleMove);
      window.removeEventListener('mouseup', handleUp);
    };

    window.addEventListener('mousemove', handleMove);
    window.addEventListener('mouseup', handleUp);
  }

  async function handleMapSearch() {
    const keyword = mapSearchQuery.trim();
    if (!keyword) return;
    setMapSearching(true);
    setError('');
    try {
      if (!window.AMap?.plugin) {
        throw new Error('高德地图搜索组件未加载');
      }

      const location = await new Promise<{ lng: number; lat: number }>((resolve, reject) => {
        window.AMap?.plugin?.(['AMap.PlaceSearch'], () => {
          if (!window.AMap?.PlaceSearch) {
            reject(new Error('高德地图搜索组件未加载'));
            return;
          }
          const placeSearch = new window.AMap!.PlaceSearch!({
            pageSize: 10,
            pageIndex: 1,
            city: '全国',
            citylimit: false,
          });
          placeSearch.search?.(keyword, (status, result) => {
            const pois = result?.poiList?.pois ?? [];
            const target = pois.find((item) => {
              const lng = item.location?.lng;
              const lat = item.location?.lat;
              return Number.isFinite(lng) && Number.isFinite(lat);
            });
            if (status === 'complete' && target?.location && Number.isFinite(target.location.lng) && Number.isFinite(target.location.lat)) {
              resolve({ lng: Number(target.location.lng), lat: Number(target.location.lat) });
              return;
            }
            reject(new Error(`未找到地点：${keyword}`));
          });
        });
      });

      const lng = Number(location.lng);
      const lat = Number(location.lat);
      if (!Number.isFinite(lng) || !Number.isFinite(lat)) throw new Error(`地点坐标解析失败：${keyword}`);
      const nextView = { center: [lng, lat] as [number, number], zoom: 16 };
      mapViewRef.current = nextView;
      pendingMapJumpRef.current = nextView;
      setMapLayerMode((current) => current ?? 'roadmap');
      if (amapInstanceRef.current) {
        amapInstanceRef.current.setCenter?.(nextView.center);
        amapInstanceRef.current.setZoom?.(nextView.zoom);
        pendingMapJumpRef.current = null;
      }
    } catch (err) {
      setError(String((err as Error).message || err));
    } finally {
      setMapSearching(false);
    }
  }

  async function handleAsk() {
    if (selectedDiagram === null) return;
    if (!question.trim()) return;
    requestAbortRef.current?.abort();
    const controller = new AbortController();
    requestAbortRef.current = controller;
    setLoading(true);
    setThinkingSteps([{ label: '准备分析任务', detail: hasDiagramShape ? '正在校验圈选区域并建立问答任务。' : '正在建立问答任务。' }]);
    setError('');
    const userMessage: ChatMessage = {
      id: crypto.randomUUID(),
      role: 'user',
      content: chatImageAttachment ? `${question}\n[图片] ${chatImageAttachment.name}` : question,
    };
    const assistantMessageId = crypto.randomUUID();
    setMessages((current) => [...current, userMessage]);
    try {
      const shape = hasDiagramShape ? buildShape() : null;
      const asksMapStatistics = isLikelyMapStatisticsQuestion(question);
      const asksAreaCalc = isLikelyAreaCalculation(question);
      const district = extractDistrict(question);
      let backendTaskHint: string | null = null;
      if (chatMode === 'analysis') {
        if (asksAreaCalc) {
          backendTaskHint = '计算面积';
        } else {
          backendTaskHint = '数据分析问答';
        }
      } else if (chatMode === 'knowledge') {
        backendTaskHint = chatImageAttachment ? '图纸+规则综合分析' : '规划文本问答';
      } else if (chatMode === 'industry') {
        backendTaskHint = resolveIndustryTaskHint(question);
      }
      const useBlockingAsk = chatMode === 'knowledge';
      setMessages((current) => [
        ...current,
        { id: assistantMessageId, role: 'assistant', content: '', meta: { shape, intent: {}, tool_results: {} } },
      ]);
      // analysis mode: area calculation requires a shape
      if (chatMode === 'analysis' && asksAreaCalc) {
        if (!hasDiagramShape) {
          setMessages((current) => current.map((message) => (
            message.id === assistantMessageId
              ? { ...message, content: '请先在图纸上圈选需要统计面积的区域。' }
              : message
          )));
          setThinkingSteps((current) => appendThinkingStep(current, { label: '缺少圈选区域', detail: '计算面积需要先在图纸上圈选范围。' }));
          return;
        }
      }
      // analysis mode: district-level POI/enterprise statistics (no shape needed)
      if (chatMode === 'analysis' && district && asksMapStatistics && !asksAreaCalc) {
        setThinkingSteps((current) => appendThinkingStep(current, { label: '统计行政区数据', detail: `正在读取 ${district} 的 POI 和企业数据。` }));
        const answer = await buildDistrictStatisticsAnswer(question, district);
        setMessages((current) => current.map((message) => (
          message.id === assistantMessageId
            ? {
                ...message,
                content: answer,
                meta: {
                  ...(message.meta ?? {}),
                  intent: { intent: 'district_statistics', source: 'local-district-stats' },
                  tool_results: { district_statistics: { status: 'success', district } },
                },
              }
            : message
        )));
        setThinkingSteps((current) => appendThinkingStep(current, { label: '统计完成', detail: `已按 ${district} 行政区划生成分类统计。` }));
        setQuestion('');
        return;
      }
      // analysis mode: map range statistics with drawn shape
      if (chatMode === 'analysis' && asksMapStatistics && mapShape) {
        setThinkingSteps((current) => appendThinkingStep(current, { label: '统计地图数据', detail: '正在读取圈选范围内的 POI 和企业数据。' }));
        const answer = await buildMapRangeStatisticsAnswer(question, mapShape);
        setMessages((current) => current.map((message) => (
          message.id === assistantMessageId
            ? {
                ...message,
                content: answer,
                meta: {
                  ...(message.meta ?? {}),
                  intent: { intent: 'map_range_statistics', source: 'local-map-analysis' },
                  tool_results: { map_range_statistics: { status: 'success' } },
                },
              }
            : message
        )));
        setThinkingSteps((current) => appendThinkingStep(current, { label: '统计完成', detail: '已按圈选范围生成分类统计。' }));
        setQuestion('');
        return;
      }
      // industry mode: enterprise statistics in selection/bbox (only for pure stats questions, not direction/chain)
      if (chatMode === 'industry' && asksMapStatistics && mapShape && backendTaskHint === '企业统计') {
        setThinkingSteps((current) => appendThinkingStep(current, { label: '统计地图数据', detail: '正在读取圈选范围内的企业数据。' }));
        const answer = await buildMapRangeStatisticsAnswer(question, mapShape);
        setMessages((current) => current.map((message) => (
          message.id === assistantMessageId
            ? {
                ...message,
                content: answer,
                meta: {
                  ...(message.meta ?? {}),
                  intent: { intent: 'map_range_statistics', source: 'industry-mode-stats' },
                  tool_results: { map_range_statistics: { status: 'success' } },
                },
              }
            : message
        )));
        setThinkingSteps((current) => appendThinkingStep(current, { label: '统计完成', detail: '已按圈选范围生成分类统计。' }));
        setQuestion('');
        return;
      }
      if (chatMode === 'industry' && asksMapStatistics && !mapShape && backendTaskHint === '企业统计') {
        const noShapeAnswer = '请先在地图上圈选或缩放到目标区域，然后再统计企业类型和数量。';
        setMessages((current) => current.map((message) => (
          message.id === assistantMessageId ? { ...message, content: noShapeAnswer } : message
        )));
        setQuestion('');
        return;
      }
      if (useBlockingAsk) {
        setThinkingSteps((current) => appendThinkingStep(current, { label: '连接知识库', detail: '正在等待问答结果返回。' }));
        const result = await askDiagram(selectedDiagram.id, question, shape, {
          conversationId: effectiveConversationId,
          taskHint: backendTaskHint,
          imageDataUrl: chatImageAttachment?.dataUrl ?? null,
          imageName: chatImageAttachment?.name ?? null,
        });
        if (currentConversationKey && result.conversation_id) {
          setConversationMap((current) => ({ ...current, [currentConversationKey]: result.conversation_id as string }));
        }
        setMessages((current) => current.map((message) => (
          message.id === assistantMessageId
            ? { ...message, content: result.answer, meta: { ...(message.meta ?? {}), intent: result.intent, tool_results: result.tool_results } }
            : message
        )));
        setThinkingSteps((current) => appendThinkingStep(current, { label: '答复生成完成', detail: '规划结果已整理完毕。' }));
      } else {
        const mapBbox = (() => {
          if (chatMode !== 'industry' || !amapInstanceRef.current) return undefined;
          const bounds = amapInstanceRef.current.getBounds?.();
          if (!bounds) return undefined;
          const sw = bounds.getSouthWest();
          const ne = bounds.getNorthEast();
          return { west: sw.lng, south: sw.lat, east: ne.lng, north: ne.lat };
        })();
        const mapSelection = chatMode === 'industry' && mapShape ? mapShape : undefined;
        await streamAskDiagram(selectedDiagram.id, question, shape, {
          conversationId: effectiveConversationId,
          taskHint: backendTaskHint,
          imageDataUrl: chatImageAttachment?.dataUrl ?? null,
          imageName: chatImageAttachment?.name ?? null,
          signal: controller.signal,
          mapBbox: mapBbox ?? undefined,
          mapSelection: mapSelection ?? undefined,
        }, {
          onEvent: (event: AskStreamEvent) => {
            if (event.type === 'status') {
              const stepMap = {
                classify: { label: '识别提问意图', detail: event.message },
                tools: { label: '执行规划分析工具', detail: event.message },
                answer: { label: '组织规划答复', detail: event.message },
              } as const;
              const nextStep = stepMap[event.stage];
              setThinkingSteps((current) => appendThinkingStep(current, nextStep));
              return;
            }
            if (event.type === 'intent') {
              setThinkingSteps((current) => appendThinkingStep(current, { label: '意图识别完成', detail: event.message }));
              setMessages((current) => current.map((message) => (
                message.id === assistantMessageId
                  ? { ...message, meta: { ...(message.meta ?? {}), intent: event.intent } }
                  : message
              )));
              return;
            }
            if (event.type === 'tool_result') {
              setThinkingSteps((current) => appendThinkingStep(current, { label: `${event.tool} 已完成`, detail: event.message }));
              setMessages((current) => current.map((message) => (
                message.id === assistantMessageId
                  ? {
                      ...message,
                      meta: {
                        ...(message.meta ?? {}),
                        tool_results: {
                          ...(((message.meta ?? {}).tool_results as Record<string, unknown> | undefined) ?? {}),
                          [event.tool]: event.result,
                        },
                      },
                    }
                  : message
              )));
              if (event.tool === 'industry_relation' && (event.result as Record<string, unknown>)?.related_companies) {
                applyRelationColors((event.result as Record<string, unknown>).related_companies as Array<{ id: number; name: string; lng: number; lat: number; relation: string; industry: string }>);
              }
              return;
            }
            if (event.type === 'tool_results') {
              setMessages((current) => current.map((message) => (
                message.id === assistantMessageId
                  ? { ...message, meta: { ...(message.meta ?? {}), tool_results: event.tool_results } }
                  : message
              )));
              return;
            }
            if (event.type === 'answer_delta') {
              setMessages((current) => current.map((message) => (
                message.id === assistantMessageId
                  ? { ...message, content: `${message.content}${event.delta}` }
                  : message
              )));
              return;
            }
            if (event.type === 'conversation') {
              if (currentConversationKey) {
                setConversationMap((current) => ({ ...current, [currentConversationKey]: event.conversation_id }));
              }
              return;
            }
            if (event.type === 'final') {
              if (currentConversationKey && event.conversation_id) {
                setConversationMap((current) => ({ ...current, [currentConversationKey]: event.conversation_id as string }));
              }
              setMessages((current) => current.map((message) => (
                message.id === assistantMessageId
                  ? { ...message, content: event.answer, meta: { ...(message.meta ?? {}), intent: event.intent, tool_results: event.tool_results } }
                  : message
              )));
              setThinkingSteps((current) => appendThinkingStep(current, { label: '答复生成完成', detail: '规划结果已整理完毕。' }));
              return;
            }
            if (event.type === 'error') {
              setError(event.message);
            }
          },
        });
      }
      setQuestion('');
      setChatImageAttachment(null);
    } catch (err) {
      if ((err as Error).name === 'AbortError') {
        setThinkingSteps((current) => appendThinkingStep(current, { label: '分析已停止', detail: '已终止本次分析，可直接发起下一轮提问。' }));
        return;
      }
      const message = String((err as Error).message || err);
      setError(message);
      setMessages((current) => [...current, { id: crypto.randomUUID(), role: 'assistant', content: '抱歉，目前检索不到' }]);
    } finally {
      requestAbortRef.current = null;
      setLoading(false);
    }
  }

  async function handleChatImagePick(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    const allowedTypes = new Set(['image/png', 'image/jpeg']);
    if (!allowedTypes.has(file.type)) {
      setError('规划对话仅支持上传 jpg/png 图片');
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      setError('图片不能超过 10MB');
      return;
    }
    try {
      const dataUrl = await readFileAsDataUrl(file);
      setChatImageAttachment({ name: file.name, dataUrl, mimeType: file.type });
      setError('');
    } catch (err) {
      setError(String((err as Error).message || err));
    }
  }

  function handleStopAsk() {
    requestAbortRef.current?.abort();
    requestAbortRef.current = null;
    setLoading(false);
  }

  function focusCompany(company: CompanyPoint) {
    setSelectedCompanyId(company.id);
    amapInstanceRef.current?.setCenter?.([company.lng, company.lat]);
    companyMarkerMapRef.current.get(company.id)?.emit?.('click');
  }

  function clearCompanyMarkers() {
    companyMarkerMapRef.current.forEach((marker) => marker.setMap?.(null));
    companyMarkerMapRef.current.clear();
  }

  function clearPoiMarkers() {
    poiInfoWindowRef.current?.close?.();
    poiMarkerMapRef.current.forEach((marker) => marker.setMap?.(null));
    poiMarkerMapRef.current.clear();
  }

  function clearRelationColors() {
    companyRelationMapRef.current.clear();
    setShowRelationLegend(false);
    // Restore all existing company markers to default color
    companyMarkerMapRef.current.forEach((marker) => {
      marker.setContent?.(`<div class="relation-marker-dot" style="background:${DEFAULT_MARKER_COLOR};"></div>`);
    });
  }

  function applyRelationColors(companies: Array<{ id: number; name: string; lng: number; lat: number; relation: string; industry: string }>) {
    if (!companies?.length) return;
    // Build relation map
    companyRelationMapRef.current.clear();
    for (const company of companies) {
      companyRelationMapRef.current.set(company.id, company.relation);
    }
    // Re-color all existing company markers
    companyMarkerMapRef.current.forEach((marker, id) => {
      const relation = companyRelationMapRef.current.get(id);
      const color = relation ? (RELATION_COLORS[relation] || RELATION_COLORS.other) : DEFAULT_MARKER_COLOR;
      marker.setContent?.(`<div class="relation-marker-dot" style="background:${color};"></div>`);
    });
    setShowRelationLegend(true);
  }

  function clearLandUsePolygons() {
    landUsePolygonMapRef.current.forEach((polygon) => polygon.setMap?.(null));
    landUsePolygonMapRef.current.clear();
    hoveredLandUseFeatureRef.current = null;
    selectedLandUseFeatureRef.current = null;
  }

  function togglePoiCategory(categoryName: string) {
    setEnabledPoiCategories((current) => (
      current.includes(categoryName)
        ? current.filter((item) => item !== categoryName)
        : [...current, categoryName]
    ));
  }

  function handleLibraryResizeStart(event: ReactMouseEvent<HTMLDivElement>) {
    beginDrag(event, (moveEvent) => {
      const rect = workspaceRef.current?.getBoundingClientRect();
      if (!rect || libraryCollapsed) return;
      const next = snapSize(clamp(moveEvent.clientX - rect.left, LIBRARY_WIDTH_RANGE.min, LIBRARY_WIDTH_RANGE.max), LIBRARY_WIDTH_RANGE.snaps);
      setLibraryWidth(next);
      setDragHint({ label: '图纸库', value: next, unit: 'px', x: moveEvent.clientX, y: moveEvent.clientY });
    }, () => setDragHint(null));
  }

  function handleChatResizeStart(event: ReactMouseEvent<HTMLDivElement>) {
    beginDrag(event, (moveEvent) => {
      const rect = workspaceRef.current?.getBoundingClientRect();
      if (!rect) return;
      const next = snapSize(clamp(rect.right - moveEvent.clientX, CHAT_WIDTH_RANGE.min, CHAT_WIDTH_RANGE.max), CHAT_WIDTH_RANGE.snaps);
      setChatWidth(next);
      setDragHint({ label: '对话区', value: next, unit: 'px', x: moveEvent.clientX, y: moveEvent.clientY });
    }, () => setDragHint(null));
  }

  function handleCompanyDrawerResizeStart(event: ReactMouseEvent<HTMLDivElement>) {
    beginDrag(event, (moveEvent) => {
      const rect = workbenchMainRef.current?.getBoundingClientRect();
      if (!rect || !showCompanyPanel || !showMapLayer) return;
      const next = snapSize(clamp(rect.right - moveEvent.clientX, COMPANY_DRAWER_WIDTH_RANGE.min, COMPANY_DRAWER_WIDTH_RANGE.max), COMPANY_DRAWER_WIDTH_RANGE.snaps);
      setCompanyDrawerWidth(next);
      setDragHint({ label: '企业面板', value: next, unit: 'px', x: moveEvent.clientX, y: moveEvent.clientY });
    }, () => setDragHint(null));
  }

  function handleBelowInfoResizeStart(event: ReactMouseEvent<HTMLDivElement>) {
    beginDrag(event, (moveEvent) => {
      const rect = mapWorkbenchRef.current?.getBoundingClientRect();
      if (!rect) return;
      const next = snapSize(clamp(rect.bottom - moveEvent.clientY, BELOW_INFO_HEIGHT_RANGE.min, BELOW_INFO_HEIGHT_RANGE.max), BELOW_INFO_HEIGHT_RANGE.snaps);
      setBelowInfoCollapsed(false);
      setBelowInfoHeight(next);
      setDragHint({ label: '比例尺与图例', value: next, unit: 'px', x: moveEvent.clientX, y: moveEvent.clientY });
    }, () => setDragHint(null));
  }

  return (
    <div className="app-shell">
      <header className="topbar workspace-topbar">
        <div>
          <h1>轻量化规划AI总师协同平台</h1>
          <p>图纸识别 · 区域圈选 · 多轮规划问答</p>
        </div>
        <div className="top-status">
          <span>{selectedDiagram ? selectedDiagram.filename : '未选择图纸'}</span>
          <span>{hasShape ? '已圈选区域' : '未圈选'}</span>
        </div>
      </header>

      <main
        ref={workspaceRef}
        className={libraryCollapsed ? 'workspace collapsed-library' : 'workspace'}
        style={{ gridTemplateColumns: workspaceColumns }}
      >
        <div className="library-sidebar">
          <DiagramLibrary
            diagrams={diagrams}
            selectedId={selectedId}
            onSelect={(id) => { setSelectedId(id); resetShape(); }}
            onUpload={handleUpload}
            collapsed={libraryCollapsed}
            onToggle={() => setLibraryCollapsed((value) => !value)}
            onRename={handleRenameDiagram}
            onDelete={handleDeleteDiagram}
          />
          {!libraryCollapsed && (
            <div className="layer-dock sidebar-layer-dock">
              <div className="layer-dock-head">
                <div className="layer-dock-title">图层控制</div>
              </div>
              <button
                className={mapLayerMode === 'roadmap' ? 'layer-toggle active' : 'layer-toggle'}
                onClick={() => setMapLayerMode((value) => (value === 'roadmap' ? null : 'roadmap'))}
              >
                高德地图
              </button>
              <button
                className={mapLayerMode === 'satellite' ? 'layer-toggle active' : 'layer-toggle'}
                onClick={() => setMapLayerMode((value) => (value === 'satellite' ? null : 'satellite'))}
              >
                卫星影像
              </button>
              {selectedDiagram && (
                <button
                  className={showDiagramLayer ? 'layer-toggle active' : 'layer-toggle'}
                  onClick={() => setShowDiagramLayer((value) => !value)}
                >
                  图纸信息
                </button>
              )}
              <button
                className={showLandUseLayer ? 'layer-toggle active' : 'layer-toggle'}
                onClick={() => setShowLandUseLayer((value) => !value)}
                disabled={!showMapLayer}
              >
                土地利用
              </button>
              <button
                className={showCompanyLayer ? 'layer-toggle active group-toggle' : 'layer-toggle group-toggle'}
                onClick={() => {
                  setShowCompanyLayer((value) => {
                    const next = !value;
                    setShowCompanyPanel(next);
                    return next;
                  });
                }}
                disabled={!showMapLayer}
              >
                <span className="group-toggle-label">企业数据</span>
                {showCompanyLayer && (
                  <span
                    className="group-toggle-tri"
                    onClick={(event) => {
                      event.stopPropagation();
                      toggleLayerSub('company');
                    }}
                  >
                    {layerSubOpen.has('company') ? '▼' : '▶'}
                  </span>
                )}
              </button>
              {showCompanyLayer && layerSubOpen.has('company') && (
                <div className="layer-group-children">
                  {RELATION_ORDER.map((key) => {
                    const color = RELATION_COLORS[key];
                    const active = companyCategoryVisible.has(key);
                    return (
                      <div key={key} className={active ? 'layer-sub-toggle-row active' : 'layer-sub-toggle-row'} onClick={() => toggleCompanyCategory(key)}>
                        <span className="relation-legend-dot" style={{ background: color }} />
                        <span className="layer-sub-toggle-label">{RELATION_LABELS[key]}</span>
                        <span className={active ? 'layer-sub-switch on' : 'layer-sub-switch'} />
                      </div>
                    );
                  })}
                </div>
              )}
              <button
                className={showPoiLayer ? 'layer-toggle active group-toggle' : 'layer-toggle group-toggle'}
                onClick={() => setShowPoiLayer((value) => !value)}
                disabled={!showMapLayer}
              >
                <span className="group-toggle-label">POI数据</span>
                {showPoiLayer && (
                  <span
                    className="group-toggle-tri"
                    onClick={(event) => {
                      event.stopPropagation();
                      toggleLayerSub('poi');
                    }}
                  >
                    {layerSubOpen.has('poi') ? '▼' : '▶'}
                  </span>
                )}
              </button>
              {showPoiLayer && layerSubOpen.has('poi') && (
                <div className="layer-group-children">
                  {poiCategories.length === 0 ? (
                    <div className="muted-sub">正在加载POI分类...</div>
                  ) : (
                    poiCategories.map((category) => {
                      const active = enabledPoiCategories.includes(category.name);
                      const color = poiCategoryColorMap[category.name] ?? POI_CATEGORY_COLORS[0];
                      return (
                        <div key={category.name} className={active ? 'layer-sub-toggle-row active' : 'layer-sub-toggle-row'} onClick={() => togglePoiCategory(category.name)}>
                          <span className="relation-legend-dot" style={{ background: color }} />
                          <span className="layer-sub-toggle-label">{category.name}</span>
                          <span className={active ? 'layer-sub-switch on' : 'layer-sub-switch'} />
                        </div>
                      );
                    })
                  )}
                </div>
              )}
            </div>
          )}
        </div>
        <div
          className={libraryCollapsed ? 'panel-resizer hidden' : 'panel-resizer'}
          onMouseDown={handleLibraryResizeStart}
        />

        <section ref={mapWorkbenchRef} className="map-workbench">
          <div className="map-toolbar-row">
            <div className="map-tool-group">
              <span className="map-tool-label">圈选区域：</span>
              <button className={mode === 'polygon' ? 'map-tool-btn active' : 'map-tool-btn'} onClick={handlePolygonToolClick} title="多边形">多边形</button>
              <button className={mode === 'rectangle' ? 'map-tool-btn active' : 'map-tool-btn'} onClick={handleRectangleToolClick} title="矩形">矩形</button>
              <button className={mode === 'circle' && (!isMapShapeTarget || mapCircleDrawingEnabled) ? 'map-tool-btn active' : 'map-tool-btn'} onClick={handleCircleToolClick} title="圆形">圆形</button>
              <button className="map-tool-btn danger" onClick={() => { setMapCircleDrawingEnabled(false); resetShape(); }} title="清空">清空</button>
            </div>
            <div className="map-search-mini">
              <input
                className="map-search-input"
                value={mapSearchQuery}
                onChange={(event) => setMapSearchQuery(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') {
                    event.preventDefault();
                    void handleMapSearch();
                  }
                }}
                placeholder="搜索地点并跳转"
              />
              <button className="map-search-btn" onClick={() => void handleMapSearch()} disabled={mapSearching}>
                {mapSearching ? '搜索中' : '跳转'}
              </button>
            </div>
          </div>
          {(mode === 'circle' || mode === 'rectangle') && (
            <div className="map-hint-bar">
              {mode === 'circle'
                ? (isMapShapeTarget ? (mapCircleDrawingEnabled ? '拖拽绘制圆形范围' : '圆形绘制已关闭，左键可拖动地图') : '先单击圆心，再拖拽调整半径')
                : (isMapShapeTarget ? '拖拽框选矩形范围' : '按住左键拖拽框选矩形区域')}
            </div>
          )}
          <div
            ref={workbenchMainRef}
            className={showCompanyPanel && showMapLayer ? 'workbench-main with-company-drawer' : 'workbench-main'}
            style={{ gridTemplateColumns: workbenchColumns }}
          >
          <div className="viewer">
            <div className="image-wrap">
              <div className="image-stage layer-stage">
                  {showMapLayer && <div ref={amapContainerRef} className="amap-canvas map-stage-layer" />}
                  {mapCircleMetrics && (
                    <div className="map-radius-editor-card">
                      <div className="map-radius-editor-title">
                        <span>圆形范围半径</span>
                        <strong>{mapCircleMetrics.radiusKm.toFixed(3)} km</strong>
                      </div>
                      <label className="radius-editor-field">
                        <span>手动输入 km</span>
                        <input
                          type="number"
                          min="0"
                          step="0.001"
                          value={mapCircleRadiusKmInput}
                          onMouseDown={(event) => event.stopPropagation()}
                          onClick={(event) => event.stopPropagation()}
                          onFocus={() => setEditingMapCircleRadius(true)}
                          onBlur={(event) => {
                            updateMapCircleRadiusByKilometers(event.target.value);
                            setEditingMapCircleRadius(false);
                          }}
                          onChange={(event) => updateMapCircleRadiusByKilometers(event.target.value)}
                          onKeyDown={(event) => {
                            event.stopPropagation();
                            if (event.key === 'Enter') {
                              event.preventDefault();
                              updateMapCircleRadiusByKilometers((event.currentTarget as HTMLInputElement).value);
                              setEditingMapCircleRadius(false);
                              (event.currentTarget as HTMLInputElement).blur();
                            }
                          }}
                        />
                      </label>
                      <div className="radius-editor-meta">
                        <span>直径</span>
                        <strong>{mapCircleMetrics.diameterKm.toFixed(3)} km</strong>
                      </div>
                    </div>
                  )}
                  {!showMapLayer && !showDiagramLayer && <div className="empty-layer-tip">请至少开启一个图层</div>}
                  {selectedDiagram && showDiagramLayer && (
                    <div className="diagram-stage-layer">
                      <div className="diagram-zoom-toolbar">
                        <div className="diagram-zoom-group">
                          <button className="dock-mini-btn" onClick={handleZoomOut} disabled={viewerZoom <= DIAGRAM_ZOOM_MIN}>-</button>
                          <button className="dock-mini-btn" onClick={handleZoomReset}>{Math.round(viewerZoom * 100)}%</button>
                          <button className="dock-mini-btn" onClick={handleZoomIn} disabled={viewerZoom >= DIAGRAM_ZOOM_MAX}>+</button>
                        </div>
                      </div>
                      <div
                        ref={diagramViewportRef}
                        className={panningDiagram ? 'diagram-viewport panning' : 'diagram-viewport'}
                        onWheel={handleDiagramWheel}
                        onMouseDown={handleDiagramViewportMouseDown}
                      >
                        <div
                          className="diagram-canvas"
                          style={{ width: `${zoomedCanvasSize.width}px`, height: `${zoomedCanvasSize.height}px` }}
                        >
                          <img
                            className={showMapLayer ? 'diagram-layer atop-map' : 'diagram-layer'}
                            src={diagramImageUrl(selectedDiagram.id)}
                            alt={selectedDiagram.filename}
                            style={{ width: `${zoomedCanvasSize.width}px`, height: `${zoomedCanvasSize.height}px` }}
                          />
                          <svg
                            ref={overlayRef}
                            className={mode === 'rectangle' && draggingRectangle ? 'overlay crosshair-mode' : circleDragMode === 'move-center' ? 'overlay move-mode' : circleDragMode === 'resize' ? 'overlay resize-mode' : 'overlay'}
                            viewBox={`0 0 ${displaySize.width} ${displaySize.height}`}
                            onClick={handleOverlayClick}
                            onContextMenu={handleOverlayContextMenu}
                            onMouseDown={(event) => {
                              handleCircleDown(event);
                              handleRectangleDown(event);
                            }}
                            onMouseMove={(event) => {
                              handleCircleMove(event);
                              handleRectangleMove(event);
                            }}
                            onMouseUp={() => {
                              handleCircleUp();
                              handleRectangleUp();
                            }}
                            onMouseLeave={() => {
                              handleCircleUp();
                              handleRectangleUp();
                            }}
                          >
                            {mode !== 'rectangle' && points.length > 0 && (
                              <polygon
                                points={points.map((point) => {
                                  const displayPoint = imagePointToDisplay(point);
                                  return `${displayPoint.x},${displayPoint.y}`;
                                }).join(' ')}
                                fill="rgba(52, 152, 219, 0.2)"
                                stroke="#3498db"
                                strokeWidth={overlayVisuals.polygonStrokeWidth}
                              />
                            )}
                            {mode === 'polygon' && points.map((point, index) => {
                              const displayPoint = imagePointToDisplay(point);
                              return <circle key={index} cx={displayPoint.x} cy={displayPoint.y} r={overlayVisuals.pointRadius} fill="#e74c3c" />;
                            })}
                            {mode === 'rectangle' && rectanglePoints.length > 0 && (
                              <>
                                <polygon
                                  points={rectanglePoints.map((point) => {
                                    const displayPoint = imagePointToDisplay(point);
                                    return `${displayPoint.x},${displayPoint.y}`;
                                  }).join(' ')}
                                  fill="rgba(52, 152, 219, 0.2)"
                                  stroke="#3498db"
                                  strokeWidth={overlayVisuals.polygonStrokeWidth}
                                />
                                {rectanglePoints.map((point, index) => {
                                  const displayPoint = imagePointToDisplay(point);
                                  return <circle key={`rect-${index}`} cx={displayPoint.x} cy={displayPoint.y} r={overlayVisuals.pointRadius} fill="#e74c3c" />;
                                })}
                              </>
                            )}
                            {circle && (
                            <>
                              <circle cx={circleMetrics?.center.x ?? 0} cy={circleMetrics?.center.y ?? 0} r={circleMetrics?.radiusDisplayPx ?? 0} fill="rgba(46, 204, 113, 0.15)" stroke="#2ecc71" strokeWidth={overlayVisuals.circleStrokeWidth} />
                              <line x1={circleMetrics?.center.x ?? 0} y1={circleMetrics?.center.y ?? 0} x2={circleMetrics?.edge.x ?? 0} y2={circleMetrics?.edge.y ?? 0} stroke="#34d399" strokeWidth={overlayVisuals.guideStrokeWidth} strokeDasharray={overlayVisuals.guideDasharray} />
                              <line x1={(circleMetrics?.center.x ?? 0) - overlayVisuals.crosshairHalfSize} y1={circleMetrics?.center.y ?? 0} x2={(circleMetrics?.center.x ?? 0) + overlayVisuals.crosshairHalfSize} y2={circleMetrics?.center.y ?? 0} stroke="#ecfdf5" strokeWidth={overlayVisuals.guideStrokeWidth} />
                              <line x1={circleMetrics?.center.x ?? 0} y1={(circleMetrics?.center.y ?? 0) - overlayVisuals.crosshairHalfSize} x2={circleMetrics?.center.x ?? 0} y2={(circleMetrics?.center.y ?? 0) + overlayVisuals.crosshairHalfSize} stroke="#ecfdf5" strokeWidth={overlayVisuals.guideStrokeWidth} />
                              <circle
                                className="circle-center-handle"
                                cx={circleMetrics?.center.x ?? 0}
                                cy={circleMetrics?.center.y ?? 0}
                                r={overlayVisuals.handleRadius}
                                fill="#ecfdf5"
                                stroke="#047857"
                                strokeWidth={overlayVisuals.handleStrokeWidth}
                                onMouseDown={handleCircleCenterDown}
                              />
                              <circle
                                className="circle-radius-handle"
                                cx={circleMetrics?.edge.x ?? 0}
                                cy={circleMetrics?.edge.y ?? 0}
                                r={overlayVisuals.handleRadius}
                                fill="#34d399"
                                stroke="#064e3b"
                                strokeWidth={overlayVisuals.handleStrokeWidth}
                                onMouseDown={handleCircleRadiusHandleDown}
                              />
                            </>
                            )}
                          </svg>
                        </div>
                      </div>
                      {circleMetrics && draggingCircle && (
                        <div
                          className="radius-drag-badge"
                          style={{
                            left: `${Math.min(circleMetrics.edge.x + 14, Math.max(12, displaySize.width - 170))}px`,
                            top: `${Math.min(circleMetrics.edge.y + 14, Math.max(12, displaySize.height - 56))}px`,
                          }}
                        >
                          <strong>{circleMetrics.radiusImagePx.toFixed(1)} 原图px</strong>
                          <span>{circleMetrics.radiusMeters !== null && circleMetrics.radiusMeters !== undefined ? `${circleMetrics.radiusMeters.toFixed(2)} m` : '比例尺不可用'}</span>
                        </div>
                      )}
                      {circleMetrics && !draggingCircle && (
                        <div
                          className="radius-editor-card"
                          style={{
                            left: `${Math.min(circleMetrics.edge.x + 14, Math.max(12, displaySize.width - 220))}px`,
                            top: `${Math.min(circleMetrics.edge.y + 14, Math.max(12, displaySize.height - 110))}px`,
                          }}
                        >
                          <label className="radius-editor-field">
                            <span>半径 原图px</span>
                            <input
                              type="number"
                              min="0"
                              step="1"
                              value={circleRadiusImageInput}
                              onMouseDown={(event) => event.stopPropagation()}
                              onClick={(event) => event.stopPropagation()}
                              onFocus={() => setEditingCircleRadiusField('image')}
                              onBlur={() => setEditingCircleRadiusField((current) => (current === 'image' ? null : current))}
                              onChange={(event) => setCircleRadiusImageInput(event.target.value)}
                              onKeyDown={(event) => {
                                event.stopPropagation();
                                if (event.key === 'Enter') {
                                  event.preventDefault();
                                  updateCircleRadiusByImagePx(circleRadiusImageInput);
                                  setEditingCircleRadiusField(null);
                                  (event.currentTarget as HTMLInputElement).blur();
                                }
                              }}
                            />
                          </label>
                          <label className="radius-editor-field">
                            <span>半径 m</span>
                            <input
                              type="number"
                              min="0"
                              step="0.1"
                              value={circleRadiusMetersInput}
                              onMouseDown={(event) => event.stopPropagation()}
                              onClick={(event) => event.stopPropagation()}
                              onFocus={() => setEditingCircleRadiusField('meters')}
                              onBlur={() => setEditingCircleRadiusField((current) => (current === 'meters' ? null : current))}
                              onChange={(event) => setCircleRadiusMetersInput(event.target.value)}
                              onKeyDown={(event) => {
                                event.stopPropagation();
                                if (event.key === 'Enter') {
                                  event.preventDefault();
                                  updateCircleRadiusByMeters(circleRadiusMetersInput);
                                  setEditingCircleRadiusField(null);
                                  (event.currentTarget as HTMLInputElement).blur();
                                }
                              }}
                              disabled={!Number.isFinite(metersPerPixel) || metersPerPixel <= 0}
                            />
                          </label>
                          <div className="radius-editor-meta">
                            <span>直径</span>
                            <strong>{circleMetrics.diameterMeters !== null && circleMetrics.diameterMeters !== undefined ? `${circleMetrics.diameterMeters.toFixed(2)} m` : '—'}</strong>
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                  {!selectedDiagram && <div className="empty">请先上传或选择图纸</div>}
                </div>
              </div>
          </div>
          {showMapLayer && showCompanyLayer && showCompanyPanel && (
            <div className="panel-resizer vertical" onMouseDown={handleCompanyDrawerResizeStart} />
          )}
          {showMapLayer && showCompanyLayer && showCompanyPanel && (
            <aside className="company-drawer-panel">
              <div className="company-filter-bar">
                <div className="company-filter-top-row">
                  <button className="ghost-btn company-collapse-btn" onClick={() => setShowCompanyPanel(false)}>收起企业面板</button>
                  <select
                    className="company-filter-select"
                    value={companyDistrict}
                    onChange={(event) => setCompanyDistrict(event.target.value as (typeof COMPANY_DISTRICTS)[number])}
                  >
                    {COMPANY_DISTRICTS.map((district) => (
                      <option key={district} value={district}>
                        {district}
                      </option>
                    ))}
                  </select>
                </div>
                <input
                  className="company-filter-input"
                  value={companyKeyword}
                  onChange={(event) => setCompanyKeyword(event.target.value)}
                  placeholder="搜索企业名称"
                />
              </div>

              <div className="company-result-panel">
                <div className="company-result-head">
                  <strong>企业结果</strong>
                  <span>
                    {visibleCompanies.length === 0
                      ? '当前无结果'
                      : `${mapShape ? '当前圈选范围' : '当前视野'} ${visibleCompanies.length} 条`}
                  </span>
                </div>
                <div className="company-result-list drawer-list">
                  {visibleCompanies.length === 0 ? (
                    <div className="company-result-empty">
                      {mapShape ? '当前圈选范围内没有企业结果。' : '缩放地图或调整筛选条件后查看企业结果。'}
                    </div>
                  ) : (
                    visibleCompanies.slice(0, COMPANY_LIST_PREVIEW_LIMIT).map((company) => (
                      <button
                        key={company.id}
                        className={company.id === selectedCompanyId ? 'company-result-item active' : 'company-result-item'}
                        onClick={() => focusCompany(company)}
                      >
                        <span className="company-result-name">{company.company_name}</span>
                        <span className="company-result-meta">{company.district ?? '未知区县'} · {company.industry ?? '未知行业'}</span>
                      </button>
                    ))
                  )}
                </div>
              </div>

              <div className="company-detail-panel">
                <div className="company-detail-head">
                  <strong>企业详情</strong>
                  {selectedCompanyDetail && (
                    <button className="ghost-btn company-detail-close" onClick={() => setSelectedCompanyDetail(null)}>
                      收起
                    </button>
                  )}
                </div>
                {selectedCompanyDetail ? (
                  <div className="company-detail-body">
                    <div className="company-detail-title">{selectedCompanyDetail.company_name}</div>
                    <div className="company-detail-grid">
                      <div><b>状态</b><span>{selectedCompanyDetail.status ?? '—'}</span></div>
                      <div><b>法人</b><span>{selectedCompanyDetail.legal_representative ?? '—'}</span></div>
                      <div><b>注册资本</b><span>{selectedCompanyDetail.registered_capital ?? '—'}</span></div>
                      <div><b>所属行业</b><span>{selectedCompanyDetail.industry ?? '—'}</span></div>
                      <div><b>区县</b><span>{selectedCompanyDetail.district ?? '—'}</span></div>
                      <div><b>参保人数</b><span>{selectedCompanyDetail.insured_count ?? '—'}</span></div>
                    </div>
                    <div className="company-detail-block">
                      <b>注册地址</b>
                      <p>{selectedCompanyDetail.address ?? '—'}</p>
                    </div>
                    <div className="company-detail-block">
                      <b>经营范围</b>
                      <p>{selectedCompanyDetail.business_scope ?? '—'}</p>
                    </div>
                  </div>
                ) : (
                  <div className="company-detail-empty">点击地图点位或结果列表查看企业详情。</div>
                )}
              </div>
            </aside>
          )}
          </div>

          <div className="below-info-toggle-row">
            <button className="ghost-btn below-info-toggle-btn" onClick={() => setBelowInfoCollapsed((value) => !value)}>
              {belowInfoCollapsed ? '展开比例尺' : '折叠比例尺'}
            </button>
          </div>
          {!belowInfoCollapsed && (
            <div className="panel-resizer horizontal" onMouseDown={handleBelowInfoResizeStart} />
          )}
          {!belowInfoCollapsed && (
            <div className="below-map-info compact-info" style={{ height: `${belowInfoHeight}px` }}>
              <section className="below-scale">
                <div className="section-head">
                  <div className="section-title">比例尺</div>
                </div>
                <ScalePanel
                  key={`${selectedDiagram?.id ?? 'none'}-${selectedDiagram?.updated_at ?? 'none'}`}
                  scale={currentScale}
                  onCalibrate={handleScaleCalibration}
                  calibrating={scaleCalibrating}
                  calibrationMessage={scaleCalibrationMessage}
                />
              </section>
              <section className="below-legend">
                <div className="section-head">
                  <div className="section-title">图例</div>
                </div>
                <LegendPanel
                  legend={currentLegend}
                  scale={currentScale}
                  onRecalibrate={handleLegendRecalibration}
                  calibrating={legendCalibrating}
                  calibrationMessage={legendCalibrationMessage}
                />
              </section>
            </div>
          )}
        </section>

        <div className="panel-resizer" onMouseDown={handleChatResizeStart} />
        <ChatPanel
          messages={messages}
          question={question}
          chatMode={chatMode}
          imageAttachment={chatImageAttachment}
          loading={loading}
          disabled={selectedDiagram === null}
          onQuestionChange={setQuestion}
          onChatModeChange={setChatMode}
          onPickImage={handleChatImagePick}
          onClearImage={() => setChatImageAttachment(null)}
          onAsk={handleAsk}
          onStop={handleStopAsk}
          onClear={() => {
            setMessages([]);
            setQuestion('');
            setChatImageAttachment(null);
            clearRelationColors();
            if (selectedId !== null) {
              setConversationMap((current) => {
                const next = { ...current };
                for (const key of Object.keys(next)) {
                  if (key.startsWith(`${selectedId}:`)) delete next[key];
                }
                return next;
              });
            }
          }}
          onResetSize={() => setChatWidth(CHAT_WIDTH_RANGE.default)}
          thinkingSteps={thinkingSteps}
        />
      </main>
      {dragHint && (
        <div className="drag-size-hint" style={{ left: `${dragHint.x + 16}px`, top: `${dragHint.y + 16}px` }}>
          <strong>{dragHint.label}</strong>
          <span>{dragHint.value}{dragHint.unit}</span>
        </div>
      )}
      {error && <div className="floating-error">{error}</div>}
    </div>
  );
}

