import React from 'react';
import { useDropzone } from 'react-dropzone';
import './FileUpload.css';
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
        <p>
          <span className="cursor-target cursor-target--inline">Drag and drop your PDF files here, or click to select them</span>.
        </p>
      </div>
      <aside>
        <h4>Selected files:</h4>
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