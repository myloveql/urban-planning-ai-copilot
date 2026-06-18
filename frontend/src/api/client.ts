import type {
  AskResponse,
  AskStreamEvent,
  CompanyDetail,
  CompanyPoint,
  Diagram,
  LandUseDataset,
  OptionalRegionShape,
  PoiCategory,
  PoiPoint,
  RegionShape,
  RelatedCompany,
} from '../types';

export async function listDiagrams(): Promise<Diagram[]> {
  const response = await fetch('/api/diagrams');
  if (!response.ok) throw new Error('获取图纸列表失败');
  const data = await response.json();
  return data.items;
}

export async function uploadDiagram(file: File): Promise<Diagram> {
  const form = new FormData();
  form.append('file', file);
  const response = await fetch('/api/diagrams', { method: 'POST', body: form });
  if (!response.ok) throw new Error((await response.json()).detail || '上传失败');
  return response.json();
}

export async function renameDiagram(diagramId: number, filename: string): Promise<Diagram> {
  const response = await fetch(`/api/diagrams/${diagramId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ filename }),
  });
  if (!response.ok) throw new Error((await response.json()).detail || '修改图纸名称失败');
  return response.json();
}

export async function deleteDiagram(diagramId: number): Promise<void> {
  const response = await fetch(`/api/diagrams/${diagramId}`, {
    method: 'DELETE',
  });
  if (!response.ok) throw new Error((await response.json()).detail || '删除图纸失败');
}

export async function calibrateDiagramScale(
  diagramId: number,
  payload: {
    metersPerPixel?: number;
    referenceDistanceMeters?: number;
    referencePixelLength?: number;
    scaleText?: string;
  },
): Promise<Diagram> {
  const response = await fetch(`/api/diagrams/${diagramId}/calibrate-scale`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      meters_per_pixel: payload.metersPerPixel,
      reference_distance_meters: payload.referenceDistanceMeters,
      reference_pixel_length: payload.referencePixelLength,
      scale_text: payload.scaleText,
    }),
  });
  if (!response.ok) throw new Error((await response.json()).detail || '比例尺校正失败');
  return response.json();
}

export async function recalibrateDiagramLegend(diagramId: number): Promise<Diagram> {
  const response = await fetch(`/api/diagrams/${diagramId}/recalibrate-legend`, {
    method: 'POST',
  });
  if (!response.ok) throw new Error((await response.json()).detail || '图例重新校准失败');
  return response.json();
}

export async function askDiagram(
  diagramId: number,
  question: string,
  shape: OptionalRegionShape,
  options?: { taskHint?: string; conversationId?: string | null; imageDataUrl?: string | null; imageName?: string | null; mapBbox?: { west: number; south: number; east: number; north: number } | null; mapSelection?: RegionShape | null },
): Promise<AskResponse> {
  const response = await fetch('/api/qa/ask', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      diagram_id: diagramId,
      question,
      shape,
      task_hint: options?.taskHint,
      conversation_id: options?.conversationId ?? undefined,
      image_data_url: options?.imageDataUrl ?? undefined,
      image_name: options?.imageName ?? undefined,
      map_bbox: options?.mapBbox ?? undefined,
      map_selection: options?.mapSelection ?? undefined,
    }),
  });
  if (!response.ok) throw new Error((await response.json()).detail || '问答失败');
  return response.json();
}

export async function streamAskDiagram(
  diagramId: number,
  question: string,
  shape: OptionalRegionShape,
  options: { taskHint?: string; conversationId?: string | null; imageDataUrl?: string | null; imageName?: string | null; signal?: AbortSignal; mapBbox?: { west: number; south: number; east: number; north: number } | null; mapSelection?: RegionShape | null },
  handlers: {
    onEvent: (event: AskStreamEvent) => void;
  },
): Promise<void> {
  const response = await fetch('/api/qa/ask/stream', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
    },
    body: JSON.stringify({
      diagram_id: diagramId,
      question,
      shape,
      task_hint: options.taskHint,
      conversation_id: options.conversationId ?? undefined,
      image_data_url: options.imageDataUrl ?? undefined,
      image_name: options.imageName ?? undefined,
      map_bbox: options.mapBbox ?? undefined,
      map_selection: options.mapSelection ?? undefined,
    }),
    signal: options.signal,
  });
  if (!response.ok) throw new Error((await response.json()).detail || '流式问答失败');
  if (!response.body) throw new Error('浏览器不支持流式响应');

  const reader = response.body.getReader();
  const decoder = new TextDecoder('utf-8');
  let buffer = '';

  const flushBuffer = () => {
    const chunks = buffer.split('\n\n');
    buffer = chunks.pop() ?? '';
    for (const chunk of chunks) {
      const lines = chunk
        .split('\n')
        .filter((line) => line.startsWith('data:'))
        .map((line) => line.slice(5).trim());
      if (lines.length === 0) continue;
      const payload = lines.join('\n');
      if (!payload) continue;
      handlers.onEvent(JSON.parse(payload) as AskStreamEvent);
    }
  };

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    flushBuffer();
  }
  buffer += decoder.decode();
  flushBuffer();
}

export function diagramImageUrl(diagramId: number): string {
  return `/api/diagrams/${diagramId}/image`;
}

export async function listCompaniesInBounds(bounds: {
  minLng: number;
  minLat: number;
  maxLng: number;
  maxLat: number;
  limit?: number;
  keyword?: string;
  district?: string;
}): Promise<{ items: CompanyPoint[]; total: number; truncated: boolean }> {
  const params = new URLSearchParams({
    min_lng: String(bounds.minLng),
    min_lat: String(bounds.minLat),
    max_lng: String(bounds.maxLng),
    max_lat: String(bounds.maxLat),
    limit: String(bounds.limit ?? 500),
  });
  if (bounds.keyword && bounds.keyword.trim()) params.set('keyword', bounds.keyword.trim());
  if (bounds.district && bounds.district.trim()) params.set('district', bounds.district.trim());
  const response = await fetch(`/api/companies?${params.toString()}`);
  if (!response.ok) throw new Error('获取企业点位失败');
  return response.json();
}

export async function getCompanyDetail(companyId: number): Promise<CompanyDetail> {
  const response = await fetch(`/api/companies/${companyId}`);
  if (!response.ok) throw new Error('获取企业详情失败');
  return response.json();
}

export async function listPoiCategories(): Promise<PoiCategory[]> {
  const response = await fetch('/api/pois/categories');
  if (!response.ok) throw new Error('获取POI分类失败');
  const data = await response.json();
  return data.items;
}

export async function getLandUseDataset(): Promise<LandUseDataset> {
  const response = await fetch('/api/land-use');
  if (!response.ok) throw new Error((await response.json()).detail || '获取土地利用数据失败');
  return response.json();
}

export async function listPoisInBounds(bounds: {
  minLng: number;
  minLat: number;
  maxLng: number;
  maxLat: number;
  limit?: number;
  categories?: string[];
}): Promise<{ items: PoiPoint[]; total: number; truncated: boolean }> {
  const params = new URLSearchParams({
    min_lng: String(bounds.minLng),
    min_lat: String(bounds.minLat),
    max_lng: String(bounds.maxLng),
    max_lat: String(bounds.maxLat),
    limit: String(bounds.limit ?? 800),
  });
  for (const category of bounds.categories ?? []) {
    if (category.trim()) params.append('categories', category.trim());
  }
  const response = await fetch(`/api/pois?${params.toString()}`);
  if (!response.ok) throw new Error('获取POI点位失败');
  return response.json();
}

export interface DistrictStats<T extends string = string> {
  total: number;
  by_district: [string, number][];
  [key: string]: number | [string, number][];
}

export async function getCompanyDistrictStats(district?: string | null): Promise<DistrictStats> {
  const params = new URLSearchParams();
  if (district) params.set('district', district);
  const qs = params.toString();
  const response = await fetch(`/api/companies/district-stats${qs ? `?${qs}` : ''}`);
  if (!response.ok) throw new Error('获取企业统计失败');
  return response.json();
}

export async function getPoiDistrictStats(district?: string | null): Promise<DistrictStats> {
  const params = new URLSearchParams();
  if (district) params.set('district', district);
  const qs = params.toString();
  const response = await fetch(`/api/pois/district-stats${qs ? `?${qs}` : ''}`);
  if (!response.ok) throw new Error('获取POI统计失败');
  return response.json();
}
