import { useState } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import { Layout } from './components/Layout';
import { PriceHistoryDialog } from './components/PriceHistoryDialog';
import { CompareProvider } from './context/CompareContext';
import { AdminPage } from './pages/AdminPage';
import { ClinicDetailPage } from './pages/ClinicDetailPage';
import { ComparePage } from './pages/ComparePage';
import { MapPage } from './pages/MapPage';
import { SearchPage } from './pages/SearchPage';

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
          <Route path="/compare" element={<ComparePage />} />
          <Route path="/admin" element={<AdminPage />} />
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
