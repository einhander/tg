#filename<-c("30.03.12_7.5_500_бамбук.dat")
library(tcltk)
filename<-tk_choose.files(caption = "Choose X")

smoothing<- tk_select.list(c(1:500), preselect=c(150), title="Сглаживание")

#smoothin<-c(150)

a<-read.csv(file=filename, header=FALSE, sep="")
library(prospectr)
#mass loss
b<-movav(a$V4, w=smoothing)
#temp
#c<-movav(a$V1, w=smoothing)
#temp delta
#d<-movav(a$V2, w=smoothing)
#time
#e<-movav(a$V3, w=smoothing)



#f<-binning(c, bins=300)
temp<-binning(a$V1, bins=300)
mass<-binning(b, bins=300)
d<-movav(a$V2, w=round(smoothing/2))
deltatemp<-binning(d, bins=300)
#deltatemp<-binning(a$V2, bins=300)
time<-binning(a$V3, bins=300)

temp<-round(temp, digits=2)
time<-round(time, digits=2)
deltatemp<-round(deltatemp, digits=2)

#par(mar = c(3, 3, 3, 3) + 0.3)  # Leave space for z axis

plot(temp,mass,type="l")
par(new = T)
plot(temp,deltatemp,type="l",axes= F,col="red", xlab = NA, ylab = NA)
axis(side = 4)
mtext("Дельта Т", side=4, line=3)
f <- cbind(temp,mass,deltatemp,time)
csvfilename<-paste(filename,".csv",sep="")

write.table(f,csvfilename, row.names=FALSE, col.names=FALSE, sep="\t")
#q()
