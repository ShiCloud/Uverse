import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const distElectron = path.join(__dirname, '..', 'dist-electron');

if (!fs.existsSync(distElectron)) {
  console.error('dist-electron directory not found');
  process.exit(1);
}

const files = fs.readdirSync(distElectron);

files.forEach(file => {
  if (file.endsWith('.js')) {
    const oldPath = path.join(distElectron, file);
    const newPath = path.join(distElectron, file.replace('.js', '.cjs'));
    
    // 如果 .cjs 已存在，先删除它
    if (fs.existsSync(newPath)) {
      fs.unlinkSync(newPath);
    }
    
    if (fs.existsSync(oldPath)) {
      fs.renameSync(oldPath, newPath);
      console.log(`Renamed: ${file} -> ${file.replace('.js', '.cjs')}`);
    }
  }
});

console.log('Electron files renamed successfully');
