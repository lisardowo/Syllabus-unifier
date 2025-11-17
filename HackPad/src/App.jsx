import { useState } from 'react';
import axios from 'axios';
import FileUpload from './FileUpload.jsx';
import './App.css';

function App() {
  const [files, setFiles] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');

  const handleFilesSelected = (selectedFiles) => {
    setFiles(selectedFiles);
    setError('');
  };

  const handleSubmit = async () => {
    if (files.length === 0) {
      setError('Selecciona al menos un archivo PDF.');
      return;
    }
    setIsLoading(true);
    setError('');
    const formData = new FormData();
    files.forEach(file => {
      formData.append('files', file);
    });
    try {
      const response = await axios.post('http://localhost:8000/generar', formData, {
        responseType: 'blob',
      });
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', 'calendario_unificado.ics');
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
      setFiles([]);
    } catch (err) {
      setError('Error al generar el calendario.');
    }
    setIsLoading(false);
  };

  return (
    <div className="App">
      <h1>Generador de Calendario Académico (.ics)</h1>
      <FileUpload onFilesSelected={handleFilesSelected} />
      {error && <p style={{ color: 'red' }}>{error}</p>}
      <button onClick={handleSubmit} disabled={isLoading || files.length === 0} style={{ marginTop: '1rem' }}>
        {isLoading ? 'Generando...' : 'Generar Calendario'}
      </button>
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

export default App
