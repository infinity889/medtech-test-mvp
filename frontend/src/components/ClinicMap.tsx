import L from 'leaflet';
import { useEffect, useRef } from 'react';
import type { ClinicSummary } from '../api/types';
import { formatPriceKzt } from '../utils/format';

export interface MapClinicPoint extends ClinicSummary {
  offers_count?: number;
  min_price_kzt?: number | null;
}

interface ClinicMapProps {
  clinics: MapClinicPoint[];
  selectedClinicId?: string | null;
  onSelectClinic?: (clinicId: string) => void;
  heightClassName?: string;
}

const DEFAULT_CENTER: [number, number] = [43.238949, 76.945465]; // Almaty

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function createPinIcon(isSelected: boolean): L.DivIcon {
  const size = isSelected ? 34 : 26;
  const bg = isSelected ? '#047857' : '#0f766e';
  const ring = isSelected ? '0 0 0 4px rgba(4, 120, 87, 0.28)' : '0 2px 6px rgba(15, 23, 42, 0.35)';
  return L.divIcon({
    className: '',
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
    popupAnchor: [0, -size / 2],
    html: `<div style="width:${size}px;height:${size}px;border-radius:9999px;background:${bg};border:2.5px solid #ffffff;box-shadow:${ring};display:flex;align-items:center;justify-content:center;color:#ffffff;font-weight:700;font-size:${isSelected ? 14 : 11}px;line-height:1;">+</div>`,
  });
}

export function ClinicMap({
  clinics,
  selectedClinicId = null,
  onSelectClinic,
  heightClassName = 'h-[480px]',
}: ClinicMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const layerGroupRef = useRef<L.LayerGroup | null>(null);
  const markersRef = useRef<Map<string, L.Marker>>(new Map());

  useEffect(() => {
    const el = containerRef.current;
    if (!el || mapRef.current) return;

    const map = L.map(el, {
      center: DEFAULT_CENTER,
      zoom: 12,
      scrollWheelZoom: true,
    });

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; OpenStreetMap contributors',
      maxZoom: 19,
    }).addTo(map);

    const group = L.layerGroup().addTo(map);
    const markers = markersRef.current;
    mapRef.current = map;
    layerGroupRef.current = group;

    return () => {
      map.remove();
      mapRef.current = null;
      layerGroupRef.current = null;
      markers.clear();
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    const group = layerGroupRef.current;
    if (!map || !group) return;

    group.clearLayers();
    markersRef.current.clear();

    const geoClinics = clinics.filter(
      (c): c is MapClinicPoint & { latitude: number; longitude: number } =>
        c.latitude !== null && c.longitude !== null,
    );

    const bounds: [number, number][] = [];
    for (const clinic of geoClinics) {
      const coords: [number, number] = [clinic.latitude, clinic.longitude];
      bounds.push(coords);

      const isSelected = clinic.id === selectedClinicId;
      const marker = L.marker(coords, { icon: createPinIcon(isSelected) });

      const name = escapeHtml(clinic.clinic_name);
      const addr = escapeHtml(clinic.address ? `${clinic.city}, ${clinic.address}` : clinic.city);
      const priceLine =
        clinic.min_price_kzt !== undefined && clinic.min_price_kzt !== null
          ? `<div style="margin-top:4px;font-weight:600;color:#047857;">от ${escapeHtml(formatPriceKzt(clinic.min_price_kzt))}</div>`
          : '';
      const countLine =
        clinic.offers_count !== undefined
          ? `<div style="font-size:12px;color:#475569;">Услуг: ${clinic.offers_count}</div>`
          : '';
      const popupHtml = `
        <div style="min-width:200px;font-family:system-ui,sans-serif;line-height:1.4;">
          <div style="font-weight:700;font-size:14px;color:#0f172a;">${name}</div>
          <div style="font-size:12px;color:#475569;margin-top:2px;">${addr}</div>
          ${countLine}
          ${priceLine}
          <div style="display:flex;flex-wrap:wrap;gap:8px;margin-top:8px;font-size:12px;">
            <a href="/clinics/${encodeURIComponent(clinic.id)}" style="color:#0f766e;font-weight:600;text-decoration:underline;">Карточка</a>
            <a href="${escapeHtml(clinic.route_2gis_url)}" target="_blank" rel="noopener noreferrer" style="color:#0f172a;text-decoration:underline;">2GIS</a>
            <a href="${escapeHtml(clinic.route_google_maps_url)}" target="_blank" rel="noopener noreferrer" style="color:#0f172a;text-decoration:underline;">Google Maps</a>
          </div>
        </div>
      `;

      marker.bindPopup(popupHtml);
      marker.on('click', () => {
        onSelectClinic?.(clinic.id);
      });
      marker.addTo(group);
      markersRef.current.set(clinic.id, marker);
    }

    if (selectedClinicId && markersRef.current.has(selectedClinicId)) {
      const selectedMarker = markersRef.current.get(selectedClinicId);
      if (selectedMarker) {
        map.setView(selectedMarker.getLatLng(), Math.max(map.getZoom(), 14), { animate: true });
        selectedMarker.openPopup();
      }
    } else if (bounds.length === 1 && bounds[0]) {
      map.setView(bounds[0], 15);
    } else if (bounds.length > 1) {
      map.fitBounds(bounds, { padding: [36, 36], maxZoom: 15 });
    }
  }, [clinics, selectedClinicId, onSelectClinic]);

  return (
    <div
      ref={containerRef}
      aria-label="Интерактивная карта клиник"
      className={`w-full overflow-hidden rounded-xl border border-border bg-surface-subtle ${heightClassName}`}
    />
  );
}
