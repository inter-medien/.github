// must be loaded at the end of the body element
(function(){
	var addEvent = function(element, event, func){
			if(element.addEventListener){
				element.addEventListener(event, func, false);
			}
			else{
				element.attachEvent('on'+event, func);
			}
		},
		eventPreventDefault = function(event){
			event = event || window.event;
			if(event.preventDefault){
				event.preventDefault();
			}
			else{
				event.returnValue = false;
			}
		},
		navMainMobile = document.getElementById('nav-main-mobile'),
		navMain = document.getElementById('nav-main'),
		navMainLis, i, element, navMainTouched, touchUsed,
		navSearch = document.getElementById('nav-search');
	if(navMainMobile){
		addEvent(navMainMobile, 'change', function(){
			// Bugfix for IE to follow the base tag correctly
			var link = document.createElement('a');
			link.href = navMainMobile.value;
			document.location.href = ''+link.href;
		});
	}
	if(navSearch){
		addEvent(navSearch.getElementsByTagName('input')[0], 'focus', function(){
			navSearch.className = 'focus';
		});
		addEvent(navSearch.getElementsByTagName('button')[0], 'focus', function(){
			navSearch.className = 'focus';
		});
		addEvent(navSearch.getElementsByTagName('input')[0], 'blur', function(){
			navSearch.className = '';
		});
		addEvent(navSearch.getElementsByTagName('button')[0], 'blur', function(){
			navSearch.className = '';
		});
	}
	// dropdown fix for all touch devices
	if(window.Modernizr && Modernizr.touch){
		if(navMain && navMain.getElementsByTagName('ul').length){
			// devices supporting touch events may not mean touch input is used
			// e.g. touch enabled laptops running Windows 8
			addEvent(navMain, 'touchstart', function(event) {
				touchUsed = true;
			});
			navMainLis = navMain.getElementsByTagName('ul')[0].childNodes;
			for(i = 0; i < navMainLis.length; i++){
				if(navMainLis[i].nodeName && navMainLis[i].nodeName.toLowerCase() === 'li' && navMainLis[i].getElementsByTagName('ul').length){
					element = navMainLis[i].getElementsByTagName('a');
					if(element && (element = element[0])){
						addEvent(element, 'click', function(event){
							if(navMainTouched !== this && touchUsed){
								navMainTouched = this;
								eventPreventDefault(event);
							}
						});
					}
				}
			}
		}
	}
})();
