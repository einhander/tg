#filename<-c("30.03.12_7.5_500_бамбук.dat")
library(tcltk)
library(prospectr)
library('pspline')
library('baseline')
#library(shiny)

filename<-tk_choose.files(caption = "Choose X")
# Create the widgets
#    base <- tktoplevel()
#    list <- tklistbox(base, width = 20, height = 5)

#    entry <- tkentry(base)
#    text <- tktext(base, width = 20, height = 5)
#    tkpack(list, entry, text)
    # Write and read from the widgets
#    writeList(list, c("Option1", "Option2", "Option3"))
#    writeList(entry, "An Entry box")
#    writeText(text, "A text box")
    # Will be NULL if not selected
#    getListValue(list)
#    getTextValue(text)
#    getEntryValue(entry)
# Destroy toplevel widget
#    tkdestroy(base)

smoothing<- tk_select.list(c(1:1000), preselect=c(150), title="Сглаживание")

#smoothing<-c(150)
bins <- 300

#a<-read.csv(file=filename, header=FALSE, sep="")
termdata<-read.csv(file=filename, header=FALSE, sep="")
temp        <- termdata$V1
mass        <- movav(termdata$V4, w=smoothing)
deltatemp   <- termdata$V2
time        <- termdata$V3

#forbaseline <- cbind(deltatemp, temp)
#corrected   <- baseline(t(forbaseline))
#deltatemp  <-  c(getCorrected(corrected))

temp        <- binning(temp,     bins=bins)
mass        <- binning(mass,     bins=bins)
deltatemp   <- binning(deltatemp,bins=bins)
time        <- binning(time,     bins=bins)
#dmdt        <- binning(dmdt,     bins=1000)

temp        <- round(temp, digits=2)
time        <- round(time, digits=2)
deltatemp   <- round(deltatemp, digits=2)
mass        <- round(mass, digits=3)
#dmdt        <- as.numeric(predict(sm.spline(temp, mass), temp , 1))
dmdt <- diff(mass, differences = 1 , lag = 10)
#dmdt <- gapDer(mass, m = 1 , w = 1, s = 1)
#dmdt        <- movav(dmdt, w=smoothing)
dmdt        <- binning(dmdt,     bins=bins)



df          <- cbind(temp,mass,dmdt,deltatemp,time)

plot(temp,mass,type="l")
par(new = T)
plot(temp,deltatemp,type="l",axes= F,col="red", xlab = NA, ylab = NA)
axis(side = 4)
par(new = T)
plot(temp,m,type="l",axes= F,col="blue", xlab = NA, ylab = NA)
f <- cbind(temp,mass,deltatemp,time)
csvfilename<-paste(filename,".csv",sep="")

#write.table(f,csvfilename, row.names=FALSE, col.names=FALSE, sep="\t")
#q()
