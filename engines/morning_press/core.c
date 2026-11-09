// Physics core for morning_press (ball-ball, circle wall with optional slit, convex polygons, two-sided segments).
// Compiled automatically by sim.py (gcc -O2 -shared -fPIC core.c -o core.so -lm).
#include <math.h>
#include <string.h>
#include <stdlib.h>
#define CAUGHT 1
#define OUT 2

static int cellof(double v, double lo, double cs, int nc){ int c=(int)((v-lo)/cs); if(c<0)c=0; if(c>=nc)c=nc-1; return c; }

// polys: per poly: nv(=as double), vx, vy, w, px, py, then nv*(x,y). packed sequentially. CCW in screen coords not required: we compute orientation.
// segs: x1,y1,x2,y2
// slit: half length in px along the wall (<=0 none), at angle slit_a.
// stats[0]=wall hits, stats[1]=angle of last wall hit (unused), stats[2]=max overlap seen ball-ball
int step(int n, double *x, double *y, double *vx, double *vy, double *r, int *flag,
         double CX, double CY, double R, double slit_a, double slit_h,
         int npoly, double *polys, int nseg, double *segs,
         double V, double dt, int iters, double *stats, int *wallhit_idx)
{
    int nwh = 0;
    // side of each ball w.r.t. each segment BEFORE moving (a ball can never be pushed across a segment)
    signed char *side = (signed char*)malloc(n*(nseg>0?nseg:1));
    for(int s=0;s<nseg;s++){ double ax=segs[4*s],ay=segs[4*s+1],bx=segs[4*s+2],by=segs[4*s+3];
        for(int i=0;i<n;i++){ double cr=(bx-ax)*(y[i]-ay)-(by-ay)*(x[i]-ax); side[i*nseg+s]= cr>=0?1:-1; } }
    for (int i=0;i<n;i++){ x[i]+=vx[i]*dt; y[i]+=vy[i]*dt; }
    // grid
    double cs = 54.0, lo_x = CX-R-80, lo_y = CY-R-80; int nc = (int)((2*R+160)/cs)+1;
    int *head = (int*)malloc(sizeof(int)*nc*nc); int *next = (int*)malloc(sizeof(int)*n);
    double maxov = 0;
    for (int it=0; it<iters; it++){
        for (int k=0;k<nc*nc;k++) head[k]=-1;
        for (int i=0;i<n;i++){ if(flag[i]&OUT) continue; int c=cellof(y[i],lo_y,cs,nc)*nc+cellof(x[i],lo_x,cs,nc); next[i]=head[c]; head[c]=i; }
        for (int i=0;i<n;i++){
            if(flag[i]&OUT) continue;
            int cx=cellof(x[i],lo_x,cs,nc), cy=cellof(y[i],lo_y,cs,nc);
            for(int dy=-1;dy<=1;dy++) for(int dx=-1;dx<=1;dx++){
                int gx=cx+dx, gy=cy+dy; if(gx<0||gy<0||gx>=nc||gy>=nc) continue;
                for(int j=head[gy*nc+gx]; j>=0; j=next[j]){
                    if(j<=i) continue;
                    if((flag[i]&CAUGHT) && (flag[j]&CAUGHT)) continue;
                    double ddx=x[j]-x[i], ddy=y[j]-y[i], rr=r[i]+r[j];
                    double d2=ddx*ddx+ddy*ddy; if(d2>=rr*rr) continue;
                    double d=sqrt(d2); double nx,ny; if(d<1e-9){nx=1;ny=0;d=1e-9;} else {nx=ddx/d;ny=ddy/d;}
                    double ov=rr-d; if(it==iters-1 && ov>maxov){ maxov=ov; stats[1]=i; stats[3]=j; }
                    double mi=r[i]*r[i], mj=r[j]*r[j], s=mi+mj;
                    // caught balls are pinned (being crushed): free ball takes all the correction
                    double wi=mj/s, wj=mi/s;
                    if(flag[i]&CAUGHT){wi=0;wj=1;} if(flag[j]&CAUGHT){wi=1;wj=0;}
                    x[i]-=nx*ov*wi; y[i]-=ny*ov*wi; x[j]+=nx*ov*wj; y[j]+=ny*ov*wj;
                    double rv=(vx[j]-vx[i])*nx+(vy[j]-vy[i])*ny;
                    if(rv<0){
                        double ji, jj;
                        if(flag[i]&CAUGHT){ ji=0; jj=-2*rv; }
                        else if(flag[j]&CAUGHT){ ji=2*rv; jj=0; }
                        else { ji = 2*mj/s*rv; jj = -2*mi/s*rv; }
                        vx[i]+=ji*nx; vy[i]+=ji*ny; vx[j]+=jj*nx; vy[j]+=jj*ny;
                    }
                }
            }
        }
        // polygons
        int off=0;
        for(int p=0;p<npoly;p++){
            int nv=(int)polys[off]; double pvx=polys[off+1], pvy=polys[off+2], pw=polys[off+3], ppx=polys[off+4], ppy=polys[off+5];
            double *V2=polys+off+6;
            // orientation
            double area=0; for(int k=0;k<nv;k++){int k2=(k+1)%nv; area+=V2[2*k]*V2[2*k2+1]-V2[2*k2]*V2[2*k+1];}
            double sg = area>0?1:-1;
            for(int i=0;i<n;i++){
                if(flag[i]&(CAUGHT|OUT)) continue;
                // signed distances to edges (outward normals)
                double best=-1e18; int be=-1; int inside=1;
                double cpx=0,cpy=0,cd2=1e18;
                for(int k=0;k<nv;k++){
                    int k2=(k+1)%nv; double ax=V2[2*k],ay=V2[2*k+1],bx=V2[2*k2],by=V2[2*k2+1];
                    double ex=bx-ax, ey=by-ay, el=sqrt(ex*ex+ey*ey);
                    double onx= sg*ey/el, ony= -sg*ex/el; // outward
                    double sd=(x[i]-ax)*onx+(y[i]-ay)*ony;
                    if(sd>0) inside=0;
                    if(sd>best){best=sd;be=k;}
                    double t=((x[i]-ax)*ex+(y[i]-ay)*ey)/(el*el); if(t<0)t=0; if(t>1)t=1;
                    double qx=ax+ex*t, qy=ay+ey*t, q2=(x[i]-qx)*(x[i]-qx)+(y[i]-qy)*(y[i]-qy);
                    if(q2<cd2){cd2=q2;cpx=qx;cpy=qy;}
                }
                double nx,ny,pen;
                if(inside){
                    int k=be,k2=(k+1)%nv; double ex=V2[2*k2]-V2[2*k], ey=V2[2*k2+1]-V2[2*k+1], el=sqrt(ex*ex+ey*ey);
                    nx=sg*ey/el; ny=-sg*ex/el; pen=r[i]-best; cpx=x[i]-nx*best; cpy=y[i]-ny*best;
                } else {
                    double d=sqrt(cd2); if(d>=r[i]) continue;
                    nx=(x[i]-cpx)/d; ny=(y[i]-cpy)/d; pen=r[i]-d;
                }
                x[i]+=nx*pen; y[i]+=ny*pen;
                double ux=pvx-pw*(cpy-ppy), uy=pvy+pw*(cpx-ppx);
                double rv=(vx[i]-ux)*nx+(vy[i]-uy)*ny;
                if(rv<0){ vx[i]-=2*rv*nx; vy[i]-=2*rv*ny; }
            }
            off+=6+2*nv;
        }
        // segments (two-sided)
        for(int s=0;s<nseg;s++){
            double ax=segs[4*s],ay=segs[4*s+1],bx=segs[4*s+2],by=segs[4*s+3];
            double ex=bx-ax,ey=by-ay,el2=ex*ex+ey*ey;
            for(int i=0;i<n;i++){
                if(flag[i]&OUT) continue;
                double t=((x[i]-ax)*ex+(y[i]-ay)*ey)/el2;
                double el=sqrt(el2), nx, ny, d;
                if(t>0 && t<1){
                    double sg=side[i*nseg+s]; nx=-ey/el*sg; ny=ex/el*sg;   // normal pointing to the ball's own side
                    d=(x[i]-ax)*nx+(y[i]-ay)*ny; if(d>=r[i]) continue;
                } else {
                    double qx=t<=0?ax:bx, qy=t<=0?ay:by, dx=x[i]-qx, dy=y[i]-qy; d=sqrt(dx*dx+dy*dy);
                    if(d>=r[i]||d<1e-9) continue; nx=dx/d; ny=dy/d;
                }
                x[i]+=nx*(r[i]-d); y[i]+=ny*(r[i]-d);
                double rv=vx[i]*nx+vy[i]*ny; if(rv<0){vx[i]-=2*rv*nx;vy[i]-=2*rv*ny;}
            }
        }
        // circle wall with optional slit
        for(int i=0;i<n;i++){
            if(flag[i]&OUT) continue;
            double dx=x[i]-CX, dy=y[i]-CY, d=sqrt(dx*dx+dy*dy);
            int inslit=0;
            if(slit_h>0){
                double a=atan2(dy,dx)-slit_a; while(a>M_PI)a-=2*M_PI; while(a<-M_PI)a+=2*M_PI;
                if(fabs(a)*R < slit_h || d > R) inslit=1;
            }
            if(!inslit){
                if(d+r[i]>R){
                    double nx=dx/d, ny=dy/d; x[i]=CX+nx*(R-r[i]); y[i]=CY+ny*(R-r[i]);
                    double rv=vx[i]*nx+vy[i]*ny; if(rv>0){vx[i]-=2*rv*nx;vy[i]-=2*rv*ny; if(it==0 && nwh<4096) wallhit_idx[nwh++]=i;}
                }
            } else {
                double ha=slit_h/R;
                for(int e=-1;e<=1;e+=2){
                    double ex=CX+R*cos(slit_a+e*ha), ey=CY+R*sin(slit_a+e*ha);
                    double qx=x[i]-ex, qy=y[i]-ey, q=sqrt(qx*qx+qy*qy);
                    if(q<r[i]){ double nx=qx/q, ny=qy/q; x[i]=ex+nx*r[i]; y[i]=ey+ny*r[i];
                        double rv=vx[i]*nx+vy[i]*ny; if(rv<0){vx[i]-=2*rv*nx;vy[i]-=2*rv*ny; if(it==0 && nwh<4096) wallhit_idx[nwh++]=i;} }
                }
                double dx2=x[i]-CX, dy2=y[i]-CY; if(sqrt(dx2*dx2+dy2*dy2) > R + r[i] + 2) flag[i]|=OUT;
            }
        }
    }
    // constant speed
    for(int i=0;i<n;i++){ double s=sqrt(vx[i]*vx[i]+vy[i]*vy[i]); if(s<1e-9){vx[i]=V;vy[i]=0;} else {vx[i]*=V/s; vy[i]*=V/s;} }
    stats[0]=nwh; stats[2]=maxov;
    free(head); free(next); free(side);
    return nwh;
}
