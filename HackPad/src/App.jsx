import { useState } from 'react';
import axios from 'axios';
import FileUpload from './FileUpload.jsx';
import './App.css';
import { TargetCursor } from './TargetCursor.jsx';
import DarkVeil from './DarkVeil.jsx';

function App() {
  // Configure Axios base URL from environment (Render: set VITE_BACKEND_URL)
  // Keeps endpoints like '/syllabus' and '/generar' unchanged; only the origin is injected.
  axios.defaults.baseURL = import.meta.env.VITE_BACKEND_URL || '';
  const [files, setFiles] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');
  const [progress, setProgress] = useState(0);
  const [statusText, setStatusText] = useState('');
  const [scheduleAttached, setScheduleAttached] = useState(false);
  const [semesterStart, setSemesterStart] = useState('');

  const handleFilesSelected = (selectedFiles) => {
    setFiles(selectedFiles);
    setError('');
    setProgress(0);
    setStatusText('');
  };

  const handleSubmit = async () => {
    if (files.length === 0) {
      setError('Selecciona al menos un archivo PDF.');
      return;
    }
    setIsLoading(true);
    setError('');
    setProgress(0);
    setStatusText('Subiendo archivos...');
    const formData = new FormData();
    files.forEach(file => {
      formData.append('files', file);
    });
    if (scheduleAttached && semesterStart) {
      formData.append('semester_start', semesterStart);
    }
    try {
  // If schedule is attached, call the combined endpoint to return both (ZIP when both present)
  const endpoint = scheduleAttached ? '/generar' : '/syllabus';
      const response = await axios.post(endpoint, formData, {
        responseType: 'blob',
        onUploadProgress: (progressEvent) => {
          if (progressEvent.total) {
            setProgress(Math.round((progressEvent.loaded * 100) / progressEvent.total));
            setStatusText('Processing Files...');
          }
        }
      });
      setProgress(100);
      const contentType = response.headers['content-type'] || '';
      const disposition = response.headers['content-disposition'] || '';
      let filename = 'download';
      const match = disposition.match(/filename\s*=\s*([^;]+)/i);
      if (match && match[1]) {
        filename = match[1].replace(/\"/g, '').trim();
      } else if (contentType.includes('text/calendar')) {
        filename = 'class_schedule.ics';
      } else if (contentType.includes('application/pdf')) {
        filename = 'resumen_syllabus.pdf';
      } else if (contentType.includes('application/zip')) {
        filename = 'syllabus_and_schedule.zip';
      }
      setStatusText(`Descargando ${filename}...`);
      const url = window.URL.createObjectURL(new Blob([response.data], { type: contentType }));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', filename);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
      setFiles([]);
      setStatusText('¡Archivo generado y descargado!');
  setScheduleAttached(false);
  setSemesterStart('');
    } catch (err) {
      setError('Error al generar el archivo.');
      setStatusText('Error en el procesamiento.');
    }
    setIsLoading(false);
  };

  return (
    <div style={{ width: '100%', minHeight: '100vh', position: 'relative' }}>
      {/* Fondo DarkVeil fijo */}
      <div style={{ position: 'fixed', inset: 0, zIndex: 0, pointerEvents: 'none' }}>
        <DarkVeil
          hueShift={0}
          noiseIntensity={0.02}
          scanlineIntensity={0.08}
          scanlineFrequency={1.8}
          speed={0.5}
          warpAmount={0.02}
          resolutionScale={1}
        />
      </div>

      {/* Capa del TargetCursor (no bloquea clics) */}
      <div style={{ position: 'fixed', inset: 0, zIndex: 1, pointerEvents: 'none' }}>
        <TargetCursor
          spinDuration={2}
          hideDefaultCursor={true}
          parallaxOn={true}
        />
      </div>

      {/* Contenido interactivo por encima */}
      <div
        style={{
          position: 'relative',
          zIndex: 2,
          background: 'transparent',
          minHeight: '100vh',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <div
          className="App"
          style={{
            width: '100%',
            padding: '1rem',
            transform: 'translateY(6vh)',
          }}
        >
          <h1>Syllabus unifier and Summarizer (PDF)</h1>
          <FileUpload onFilesSelected={handleFilesSelected} />
          {error && <p style={{ color: 'red' }}>{error}</p>}
          <button
            className='cursor-target'
            onClick={handleSubmit}
            disabled={isLoading || files.length === 0}
            style={{ marginTop: '1rem' }}
          >
            {isLoading ? 'Processing...' : 'Generate Summary'}
          </button>
          {/* Checkbox directly below the button */}
          <div style={{ marginTop: '0.5rem', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px' }}>
            <label style={{ cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={scheduleAttached}
                onChange={(e) => setScheduleAttached(e.target.checked)}
                style={{ marginRight: '0.5rem' }}
              />
              Schedule attached (generate .ics)
            </label>
            <span className="tooltip">
              <span className="tooltip-button">?</span>
              <span className="tooltip-text">
                : Tick this if one of the uploaded PDFs contains your weekly schedule (days and times). We will generate an .ics calendar file you can import.
              </span>
            </span>
          </div>
          {/* Optional semester start date input */}
          {scheduleAttached && (
            <div style={{ marginTop: '0.5rem', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px' }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span>Semester start:</span>
                <input
                  type="date"
                  value={semesterStart}
                  onChange={(e) => setSemesterStart(e.target.value)}
                />
              </label>
            </div>
          )}
          {isLoading && (
            <div style={{ marginTop: '1rem', width: '100%' }}>
              <div style={{ background: '#eee', borderRadius: '8px', height: '18px', width: '60%', margin: '0 auto', overflow: 'hidden' }}>
                <div style={{ background: '#646cff', height: '100%', width: `${progress}%`, transition: 'width 0.3s' }} />
              </div>
              <div style={{ textAlign: 'center', marginTop: '4px', fontSize: '0.95em' }}>{progress}%</div>
              <div style={{ textAlign: 'center', marginTop: '4px', fontSize: '1em', color: '#646cff' }}>{statusText}</div>
            </div>
          )}
          {files.length > 0 && (
            <div style={{ marginTop: '1rem' }}>
              <h4>Files ready to process:</h4>
              <ul>
                {files.map((file) => (
                  <li key={file.name}>{file.name}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default App;
