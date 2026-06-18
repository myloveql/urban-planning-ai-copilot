export type Diagram = {
  id: number;
  filename: string;
  original_path: string;
  processed_path: string | null;
  legend_json: Record<string, string>;
  scale_json: Record<string, unknown>;
  image_width: number;
  image_height: number;
  created_at: string;
  updated_at: string;
};

export type Point = { x: number; y: number };

export type RegionShape =
  | { type: 'polygon'; points: Point[] }
  | { type: 'circle'; center: Point; radius: number };

export type AskResponse = {
  answer: string;
  intent: Record<string, unknown>;
  tool_results: Record<string, unknown>;
  conversation_id?: string | null;
};

export type OptionalRegionShape = RegionShape | null;

export type AskStreamEvent =
  | { type: 'status'; stage: 'classify' | 'tools' | 'answer'; message: string }
  | { type: 'intent'; intent: Record<string, unknown>; message: string }
  | { type: 'tool_result'; tool: string; result: Record<string, unknown>; message: string }
  | { type: 'tool_results'; tool_results: Record<string, unknown> }
  | { type: 'conversation'; conversation_id: string }
  | { type: 'answer_delta'; delta: string }
  | { type: 'final'; answer: string; intent: Record<string, unknown>; tool_results: Record<string, unknown>; conversation_id?: string | null }
  | { type: 'error'; message: string };

export type CompanyPoint = {
  id: number;
  company_name: string;
  district: string | null;
  industry: string | null;
  lng: number;
  lat: number;
  survival_status: string | null;
};

export type CompanyDetail = {
  id: number;
  company_name: string;
  status: string | null;
  legal_representative: string | null;
  registered_capital: string | null;
  paid_in_capital: string | null;
  established_at: string | null;
  district: string | null;
  industry: string | null;
  company_type: string | null;
  insured_count: string | null;
  address: string | null;
  business_scope: string | null;
  lng: number;
  lat: number;
  survival_status: string | null;
};

export type PoiPoint = {
  id: number;
  name: string;
  district: string | null;
  major_category: string | null;
  middle_category: string | null;
  minor_category: string | null;
  lng: number;
  lat: number;
};

export type PoiCategory = {
  name: string;
  count: number;
};

export type RelatedCompany = {
  id: number;
  name: string;
  lng: number;
  lat: number;
  relation: 'target' | 'upstream' | 'downstream' | 'other';
  industry: string;
};

export type LandUsePolygonFeature = {
  type: 'Feature';
  properties: {
    feature_id: number;
    interactive_label: string;
    [key: string]: unknown;
  };
  geometry:
    | {
        type: 'Polygon';
        coordinates: number[][][];
      }
    | {
        type: 'MultiPolygon';
        coordinates: number[][][][];
      };
};

export type LandUseDataset = {
  geojson: {
    type: 'FeatureCollection';
    features: LandUsePolygonFeature[];
  };
  meta: {
    feature_count: number;
    raw_feature_count: number;
    source_name: string;
    source_crs: string;
    target_crs: string;
    coordinate_mode?: string;
    has_properties: boolean;
    interactive_fields: string[];
  };
};
