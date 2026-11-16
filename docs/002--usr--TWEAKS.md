# Now
- as discussed in 002--llm--TWEAKS.md, switch from new koan each day to same koan until 'Next' is pressed.
- implement night mode - default to system
- header: create simple header - h1 18px Daily Koan, right justified h2 16px "an alfApp"
- create settings drawer: 
  - toggle between new koan daily and held koan
  - time of day for notification   
  - night mode 
- create analysis doc 003 - in my initial setup i am pulling a random koan from a list, but that ignores the fact that they progress. Do some research and make proposals for how we can structure Next Koan to go through gates.  But it is also possible to jump between texts. this is where id like your research - how can we updated the data model to account for levels. 
Phase 1 should simply follow this:"A common approach is to start with the Mumonkan, since its 48 cases are short and the usual entry point, then move to the Blue Cliff Record or Book of Serenity, which add layers of commentary and verse." while we consider a phase 2 that is many texts. 
Your research can also fill out all the koans from these seminal texts.
Settings should also appear to change from the above progression, to an inter-text progression, to random.
  - action items
      - fill out koans from 3 texts: mumonkan, blue cliff and/or Book of Serenity
      - create order instead of random
      - add a 'random koan' button, next koan will go back to order
- analyze:  A lot of work went into serving the same koan to all subs. Is that complexity able to be componentized? I'm concerned about potentially unnecessary complexity. 

# Later
- improve alerts icons
    - right now it's a helmet, it should be a bell.
    - when clicked, it has a checkmark icon which looses original menaing. 
- advanced order/random