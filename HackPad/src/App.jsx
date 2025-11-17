import { useState } from 'react';
import axios from 'axios';
import FileUpload from './FileUpload.jsx';
import './App.css';

function App() {
  const [files, setFiles] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');
  const [progress, setProgress] = useState(0);
  const [statusText, setStatusText] = useState('');

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
    try {
      const response = await axios.post('http://localhost:8000/generar', formData, {
        responseType: 'blob',
        onUploadProgress: (progressEvent) => {
          if (progressEvent.total) {
            setProgress(Math.round((progressEvent.loaded * 100) / progressEvent.total));
            setStatusText('Procesando archivos...');
          }
        }
      });
      setProgress(100);
      setStatusText('Creando PDF...');
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', 'resumen_syllabus.pdf');
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
      setFiles([]);
      setStatusText('¡PDF generado y descargado!');
    } catch (err) {
      setError('Error al generar el resumen del syllabus.');
      setStatusText('Error en el procesamiento.');
    }
    setIsLoading(false);
  };

  return (
    <div className="App">
      <h1>Generador de Resumen de Syllabus (PDF)</h1>
      <FileUpload onFilesSelected={handleFilesSelected} />
      {error && <p style={{ color: 'red' }}>{error}</p>}
      <button onClick={handleSubmit} disabled={isLoading || files.length === 0} style={{ marginTop: '1rem' }}>
        {isLoading ? 'Procesando...' : 'Generar Resumen'}
      </button>
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
          <h4>Archivos listos para enviar:</h4>
          <ul>
            {files.map((file) => (
              <li key={file.name}>{file.name}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export default App;
