import { Navigate, Route, Routes } from 'react-router-dom';
import { Layout } from './components/Layout';
import { CompareProvider } from './context/CompareContext';

function PlaceholderPage({ title }: { title: string }) {
  return (
    <section className="rounded-xl border border-border bg-surface p-6">
      <h1 className="text-xl font-semibold text-ink">{title}</h1>
    </section>
  );
}

export function App() {
  return (
    <CompareProvider>
      <Layout>
        <Routes>
          <Route path="/" element={<PlaceholderPage title="Поиск медицинских услуг" />} />
          <Route path="/map" element={<PlaceholderPage title="Карта клиник" />} />
          <Route path="/clinics/:clinicId" element={<PlaceholderPage title="Карточка клиники" />} />
          <Route path="/compare" element={<PlaceholderPage title="Сравнение клиник" />} />
          <Route path="/admin" element={<PlaceholderPage title="Админ-панель" />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Layout>
    </CompareProvider>
  );
}
