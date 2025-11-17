import React from 'react';
import { useDropzone } from 'react-dropzone';

function FileUpload({ onFilesSelected }) {
  const { getRootProps, getInputProps, acceptedFiles } = useDropzone({
    accept: { 'application/pdf': ['.pdf'] },
    onDrop: (files) => {
      onFilesSelected(files);
    },
    multiple: true,
  });

  return (
    <section className="file-upload">
      <div {...getRootProps({ className: 'dropzone' })}>
        <input {...getInputProps()} />
        <p>Arrastra y suelta tus archivos PDF aquí, o haz clic para seleccionarlos.</p>
      </div>
      <aside>
        <h4>Archivos seleccionados:</h4>
        <ul>
          {acceptedFiles.map(file => (
            <li key={file.path || file.name}>{file.path || file.name}</li>
          ))}
        </ul>
      </aside>
    </section>
  );
}

export default FileUpload;