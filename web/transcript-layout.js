(()=>{
 const editor=document.querySelector('#transcript');
 window.transcriptPlainText=(root=editor)=>{
  const clone=root.cloneNode(true);clone.querySelectorAll('.change-popover').forEach(n=>n.remove());
  function children(node){let text='',previousBlock=false,previousSpeech=false;for(const child of node.childNodes){const block=child.nodeType===1&&(['DIV','P'].includes(child.tagName)||child.classList.contains('transcript-turn'));const speech=child.nodeType===1&&child.classList.contains('transcript-speech');const part=read(child);if(part&&(block||previousBlock||(speech&&previousSpeech))&&text&&!text.endsWith('\n')&&!part.startsWith('\n'))text+='\n';text+=part;if(part){previousBlock=block;previousSpeech=speech;}}return text;}
  function read(node){if(node.nodeType===3)return node.textContent;if(node.nodeType!==1)return '';if(node.tagName==='BR')return '\n';let text=children(node);if(['DIV','P'].includes(node.tagName)&&!text.endsWith('\n'))text+='\n';return text;}
  return children(clone);
 };
 function outdentLine(event){
  if(event.isComposing||event.ctrlKey||event.metaKey||event.altKey)return;
  const selection=window.getSelection();if(!selection?.isCollapsed||!selection.anchorNode)return;
  const anchor=selection.anchorNode,element=anchor.nodeType===1?anchor:anchor.parentElement;
  const speech=element.closest('.transcript-speech'),turn=speech?.closest('.transcript-turn');if(!speech||!turn||!editor.contains(turn))return;
  const prefix=document.createRange();prefix.selectNodeContents(speech);prefix.setEnd(anchor,selection.anchorOffset);
  const rawPrefix=window.transcriptPlainText(prefix.cloneContents());
  const remaining=document.createRange();remaining.selectNodeContents(speech);remaining.setStart(anchor,selection.anchorOffset);
  const metadataBoundary=rawPrefix.trim()&&/^[\s\u200b]*(访谈时间|访问时间|访谈日期|访问日期|访谈形式|访问形式|访问员|访谈员|受访者)[：:]/.test(remaining.toString());
  const standaloneStart=!rawPrefix.trim()&&!turn.querySelector('.transcript-speaker')&&!turn.classList.contains('transcript-turn-unindented');
  const continuationStart=!rawPrefix.trim()&&speech!==turn.querySelector('.transcript-speech');
  const block=element.closest('div,p');const nestedBlock=block&&speech.contains(block);
  if(nestedBlock){const within=document.createRange();within.selectNodeContents(block);within.setEnd(anchor,selection.anchorOffset);if(within.toString().trim()&&!metadataBoundary)return;}
  else if((!rawPrefix.includes('\n')||rawPrefix.slice(rawPrefix.lastIndexOf('\n')+1).trim())&&!metadataBoundary&&!standaloneStart&&!continuationStart)return;
  event.preventDefault();
  if(standaloneStart){turn.classList.add('transcript-turn-unindented');editor.dispatchEvent(new InputEvent('input',{bubbles:true,inputType:'formatOutdent'}));return;}
  const tail=document.createRange();tail.selectNodeContents(speech);tail.setStart(anchor,selection.anchorOffset);
  const newTurn=document.createElement('span');newTurn.className='transcript-turn transcript-turn-unindented';newTurn.append(tail.extractContents());
  if(nestedBlock&&speech.contains(block)&&!block.textContent.trim()&&!block.querySelector('.ai-change'))block.remove();
  // Keep an explicit line boundary when the browser represented Enter using a DIV.
  if(continuationStart&&!speech.textContent.trim()&&!speech.querySelector('.ai-change'))speech.remove();
  else if(!window.transcriptPlainText(speech).endsWith('\n'))speech.append(document.createTextNode('\n'));
  turn.after(newTurn);
  // Format the field in a detached fragment, avoiding nested block wrappers.
  const fragment=document.createElement('span');fragment.append(...newTurn.childNodes);
  window.formatTranscriptTurns(fragment.textContent,fragment);
  let nextTurn=fragment.querySelector('.transcript-turn');
  if(nextTurn)newTurn.replaceWith(...fragment.childNodes);
  else {newTurn.append(...fragment.childNodes);nextTurn=newTurn;}
  if(nextTurn&&!nextTurn.querySelector('.transcript-speaker'))nextTurn.classList.add('transcript-turn-unindented');
  const caret=document.createRange();caret.selectNodeContents(nextTurn||turn);caret.collapse(true);selection.removeAllRanges();selection.addRange(caret);
  editor.dispatchEvent(new InputEvent('input',{bubbles:true,inputType:'formatOutdent'}));
 }
 editor.addEventListener('beforeinput',event=>{if(event.inputType==='deleteContentBackward')outdentLine(event);});
 editor.addEventListener('keydown',event=>{if(event.key==='Backspace'&&!event.ctrlKey&&!event.metaKey&&!event.altKey)outdentLine(event);});
 window.formatTranscriptTurns=(text,root=editor)=>{
  const labels=[...text.matchAll(/^(?:[\t ]*)(说话人\s*\d+|访谈者|受访者|访问员|访问人|提问人|采访者|[\u4e00-\u9fff]{2,5})([：:])/gm)];
  function point(offset){const walker=document.createTreeWalker(root,NodeFilter.SHOW_TEXT);let total=0,n;while(n=walker.nextNode()){if(n.parentElement.closest('.change-popover'))continue;if(offset<=total+n.length)return [n,offset-total];total+=n.length;}return null;}
  for(let i=labels.length-1;i>=0;i--){const label=labels[i],end=i+1<labels.length?labels[i+1].index:text.length;const a=point(label.index),b=point(end);if(!a||!b)continue;const range=document.createRange();range.setStart(...a);range.setEnd(...b);const turn=document.createElement('span');turn.className='transcript-turn';turn.append(range.extractContents());range.insertNode(turn);
   const walker=document.createTreeWalker(turn,NodeFilter.SHOW_TEXT);let n,total=0,last;while(n=walker.nextNode()){if(n.parentElement.closest('.change-popover'))continue;if(total+n.length>=label[0].length){last=[n,label[0].length-total];break;}total+=n.length;}
   if(!last)continue;const labelRange=document.createRange();labelRange.setStart(turn,0);labelRange.setEnd(...last);const name=document.createElement('span');name.className='transcript-speaker';name.append(labelRange.extractContents());const body=document.createElement('span');body.className='transcript-speech';body.append(...turn.childNodes);turn.replaceChildren(name,body);
  }
 };
 const sparkle='<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m12 3 2.3 6.7L21 12l-6.7 2.3L12 21l-2.3-6.7L3 12l6.7-2.3Z"/><path d="m20 2 .8 2.2L23 5l-2.2.8L20 8l-.8-2.2L17 5l2.2-.8Z"/></svg>';
 const bars='<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 19v-6M10 19V9M15 19V5M20 19V2"/></svg>';
 const ai=document.querySelector('#optimizeBtn'),analysis=document.querySelector('#goAnalysisBtn');ai.querySelector('.ai-ring')?.insertAdjacentHTML('afterend',sparkle);analysis.innerHTML=bars+'<span>分析</span>';
})();
