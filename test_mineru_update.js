const fs = require('fs');
const path = require('path');

// 模拟测试环境
const TEST_DIR = '/tmp/test_mineru';
const MODELS_DIR = path.join(TEST_DIR, 'models');
const MINERU_JSON = path.join(MODELS_DIR, 'mineru.json');

// 清理并创建测试目录
console.log('Setting up test environment...');
if (fs.existsSync(TEST_DIR)) {
  fs.rmSync(TEST_DIR, { recursive: true });
}
fs.mkdirSync(MODELS_DIR, { recursive: true });
fs.mkdirSync(path.join(MODELS_DIR, 'OpenDataLab', 'PDF-Extract-Kit-1___0'), { recursive: true });
fs.mkdirSync(path.join(MODELS_DIR, 'OpenDataLab', 'MinerU2___5-2509-1___2B'), { recursive: true });

// 创建初始的 mineru.json（带相对路径）
const initialConfig = {
  "bucket_info": {
    "bucket-name-1": ["ak", "sk", "endpoint"]
  },
  "models-dir": {
    "pipeline": "OpenDataLab/PDF-Extract-Kit-1___0",
    "vlm": "OpenDataLab/MinerU2___5-2509-1___2B"
  },
  "config_version": "1.3.1"
};

fs.writeFileSync(MINERU_JSON, JSON.stringify(initialConfig, null, 4));
console.log('Created initial mineru.json:');
console.log(fs.readFileSync(MINERU_JSON, 'utf8'));

// 模拟 config:saveToEnv 中的更新逻辑
console.log('\n--- Testing update logic ---\n');

function updateMineruJson(modelsDir) {
  const mineruJsonPath = path.join(modelsDir, 'mineru.json');
  console.log('Checking mineru.json at:', mineruJsonPath);
  console.log('mineru.json exists:', fs.existsSync(mineruJsonPath));
  
  if (fs.existsSync(mineruJsonPath)) {
    console.log('Found mineru.json, updating...');
    const mineruConfig = JSON.parse(fs.readFileSync(mineruJsonPath, 'utf-8'));
    const pipelinePath = path.join(modelsDir, 'OpenDataLab', 'PDF-Extract-Kit-1___0');
    const vlmPath = path.join(modelsDir, 'OpenDataLab', 'MinerU2___5-2509-1___2B');
    
    console.log('Pipeline path:', pipelinePath, 'exists:', fs.existsSync(pipelinePath));
    console.log('VLM path:', vlmPath, 'exists:', fs.existsSync(vlmPath));
    
    if (!mineruConfig['models-dir']) mineruConfig['models-dir'] = {};
    
    if (fs.existsSync(pipelinePath)) {
      mineruConfig['models-dir']['pipeline'] = pipelinePath;
      console.log('✓ Updated pipeline path');
    }
    if (fs.existsSync(vlmPath)) {
      mineruConfig['models-dir']['vlm'] = vlmPath;
      console.log('✓ Updated vlm path');
    }
    
    fs.writeFileSync(mineruJsonPath, JSON.stringify(mineruConfig, null, 4));
    console.log('✓ Saved mineru.json');
    return true;
  }
  return false;
}

// 执行更新
const success = updateMineruJson(MODELS_DIR);

// 验证结果
console.log('\n--- Verification ---\n');
const updatedConfig = JSON.parse(fs.readFileSync(MINERU_JSON, 'utf8'));
console.log('Updated mineru.json:');
console.log(JSON.stringify(updatedConfig, null, 4));

// 检查路径是否已更新为绝对路径
const isPipelineAbsolute = path.isAbsolute(updatedConfig['models-dir']['pipeline']);
const isVlmAbsolute = path.isAbsolute(updatedConfig['models-dir']['vlm']);

console.log('\nValidation:');
console.log('Pipeline path is absolute:', isPipelineAbsolute, '(' + updatedConfig['models-dir']['pipeline'] + ')');
console.log('VLM path is absolute:', isVlmAbsolute, '(' + updatedConfig['models-dir']['vlm'] + ')');

if (isPipelineAbsolute && isVlmAbsolute) {
  console.log('\n✅ TEST PASSED: Paths updated to absolute successfully!');
} else {
  console.log('\n❌ TEST FAILED: Paths are not absolute!');
}

// 清理
fs.rmSync(TEST_DIR, { recursive: true });
