import { useState } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import { Layout } from './components/Layout';
import { PriceHistoryDialog } from './components/PriceHistoryDialog';
import { CompareProvider } from './context/CompareContext';
import { ClinicDetailPage } from './pages/ClinicDetailPage';
import { MapPage } from './pages/MapPage';
import { SearchPage } from './pages/SearchPage';

function PlaceholderPage({ title }: { title: string }) {
  return (
    <section className="rounded-xl border border-border bg-surface p-6">
      <h1 className="text-xl font-semibold text-ink">{title}</h1>
    </section>
  );
}

interface HistoryModalState {
  serviceId: string;
  serviceName: string;
}

export function App() {
  const [historyModal, setHistoryModal] = useState<HistoryModalState | null>(null);

  function openPriceHistory(serviceId: string, serviceName: string) {
    setHistoryModal({ serviceId, serviceName });
  }

  return (
    <CompareProvider>
      <Layout>
        <Routes>
          <Route path="/" element={<SearchPage onOpenPriceHistory={openPriceHistory} />} />
          <Route path="/map" element={<MapPage />} />
          <Route
            path="/clinics/:clinicId"
            element={<ClinicDetailPage onOpenPriceHistory={openPriceHistory} />}
          />
          <Route path="/compare" element={<PlaceholderPage title="Сравнение клиник" />} />
          <Route path="/admin" element={<PlaceholderPage title="Админ-панель" />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>

        <PriceHistoryDialog
          serviceId={historyModal?.serviceId ?? null}
          serviceName={historyModal?.serviceName ?? ''}
          onClose={() => setHistoryModal(null)}
        />
      </Layout>
    </CompareProvider>
  );
}
