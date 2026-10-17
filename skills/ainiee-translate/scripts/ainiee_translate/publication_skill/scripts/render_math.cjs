// Optional: install mathjax-full in an isolated tool directory, set NODE_PATH.
// Not a general LaTeX compiler; source-verified MathJax-supported math only.
const fs = require('fs');
const {mathjax} = require('mathjax-full/js/mathjax.js');
const {TeX} = require('mathjax-full/js/input/tex.js');
const {SVG} = require('mathjax-full/js/output/svg.js');
const {liteAdaptor} = require('mathjax-full/js/adaptors/liteAdaptor.js');
const {RegisterHTMLHandler} = require('mathjax-full/js/handlers/html.js');
const {AllPackages} = require('mathjax-full/js/input/tex/AllPackages.js');
const adaptor = liteAdaptor(); RegisterHTMLHandler(adaptor);
const doc = mathjax.document('', {InputJax:new TeX({packages:AllPackages}), OutputJax:new SVG({fontCache:'none'})});
try {
  const result = adaptor.outerHTML(doc.convert(process.argv[2], {display:true}));
  if (result.includes('data-mjx-error') || result.includes('merror')) throw Error('MathJax reported a TeX error');
  const start=result.indexOf('<svg '), end=result.lastIndexOf('</svg>')+6;
  if(start<0 || end<6) throw Error('No SVG output');
  fs.writeFileSync(process.argv[3], result.slice(start,end),'utf8');
} catch(e) { console.error(String(e)); process.exit(2); }
